"""Parser and writer for BambuStudio BBS-variant 3MF files.

A 3MF file is a ZIP archive containing:
- 3D/3dmodel.model  — XML model with objects, vertices, triangles, build items
- Metadata/*.config — BBS INI-style config files (print, project, model settings)
- Metadata/plate_N.gcode — sliced G-code per plate
- Metadata/plate_N.png — thumbnail per plate

This module handles reading, modifying, and writing these archives without
external dependencies beyond the standard library.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from .settings_parser import parse_config, serialize_config

# ── Constants ──────────────────────────────────────────────────────────

MODEL_FILE = "3D/3dmodel.model"
PRINT_CONFIG = "Metadata/print_profile.config"
PROJECT_CONFIG = "Metadata/project_settings.config"
MODEL_CONFIG = "Metadata/model_settings.config"
GCODE_FORMAT = "Metadata/plate_{}.gcode"
THUMBNAIL_FORMAT = "Metadata/plate_{}.png"

NS_3MF = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"

# BBS uses a custom namespace for plate/object metadata
NS_BBS = "http://schemas.bambulab.com/package/2021"

_NS_MAP = {"m": NS_3MF, "bbs": NS_BBS}

# Minimal valid 3MF model XML template
_MINIMAL_MODEL_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<model unit="millimeter"
       xmlns="{ns3mf}"
       xmlns:bbs="{nsbbs}">
  <resources/>
  <build/>
</model>
""".format(ns3mf=NS_3MF, nsbbs=NS_BBS)


# ── Data classes ───────────────────────────────────────────────────────

@dataclass
class ObjectInfo:
    """Metadata about a single 3D object in the model."""
    id: int
    name: str
    vertex_count: int
    triangle_count: int


@dataclass
class PlateInfo:
    """Metadata about a build plate."""
    index: int
    name: str
    object_ids: list[tuple[int, int]]  # (object_id, instance_id) pairs
    has_gcode: bool
    has_thumbnail: bool


# ── Main class ─────────────────────────────────────────────────────────

class ThreeMF:
    """Read/write BambuStudio BBS-variant 3MF files.

    Usage::

        project = ThreeMF.load("my_project.3mf")
        objects = project.get_objects()
        project.set_config("Metadata/print_profile.config", "layer_height", "0.2")
        project.save("modified.3mf")
    """

    def __init__(self, path: str | None = None) -> None:
        self._files: dict[str, bytes] = {}
        self._source_path: str | None = None
        if path is not None:
            self._source_path = str(path)
            with zipfile.ZipFile(path, "r") as zf:
                for name in zf.namelist():
                    self._files[name] = zf.read(name)

    # ── Factory methods ────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str) -> ThreeMF:
        """Load a 3MF file from disk.

        Args:
            path: Path to the .3mf file.

        Returns:
            A ThreeMF instance with all archive contents in memory.

        Raises:
            FileNotFoundError: If the file does not exist.
            zipfile.BadZipFile: If the file is not a valid ZIP.
        """
        return cls(path)

    # ── Save ───────────────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """Write the 3MF archive to disk.

        Args:
            path: Output .3mf file path.
        """
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in sorted(self._files.items()):
                zf.writestr(name, data)

    # ── Object queries ─────────────────────────────────────────────────

    def get_objects(self) -> list[ObjectInfo]:
        """Parse the model XML and return all 3D objects.

        Returns:
            List of ObjectInfo with vertex/triangle counts.
        """
        root = self._parse_model()
        if root is None:
            return []

        objects: list[ObjectInfo] = []
        for obj_elem in root.findall(f".//{{{NS_3MF}}}object"):
            obj_id = int(obj_elem.get("id", "0"))
            obj_name = obj_elem.get("name", f"Object_{obj_id}")

            mesh = obj_elem.find(f"{{{NS_3MF}}}mesh")
            vcount = 0
            tcount = 0
            if mesh is not None:
                vertices = mesh.find(f"{{{NS_3MF}}}vertices")
                if vertices is not None:
                    vcount = len(vertices.findall(f"{{{NS_3MF}}}vertex"))
                triangles = mesh.find(f"{{{NS_3MF}}}triangles")
                if triangles is not None:
                    tcount = len(triangles.findall(f"{{{NS_3MF}}}triangle"))

            objects.append(ObjectInfo(
                id=obj_id,
                name=obj_name,
                vertex_count=vcount,
                triangle_count=tcount,
            ))

        return objects

    def get_plates(self) -> list[PlateInfo]:
        """Parse the model XML and return build plate information.

        Returns:
            List of PlateInfo with object assignments and gcode/thumbnail status.
        """
        root = self._parse_model()
        if root is None:
            return []

        # Collect build items grouped by plate
        plate_map: dict[int, list[tuple[int, int]]] = {}
        build = root.find(f"{{{NS_3MF}}}build")
        if build is not None:
            for item in build.findall(f"{{{NS_3MF}}}item"):
                obj_id = int(item.get("objectid", "0"))
                # BBS stores printable plate index in metadata or attributes
                plate_idx = 0
                # Check for bbs:plate_index or printable attribute
                pi_attr = item.get(f"{{{NS_BBS}}}plate_index")
                if pi_attr is not None:
                    plate_idx = int(pi_attr)
                # Instance ID from item index within plate
                inst_id = int(item.get(f"{{{NS_BBS}}}instance_id", "0"))
                plate_map.setdefault(plate_idx, []).append((obj_id, inst_id))

        # If no build items have plate indices, create plate 0 with all items
        if not plate_map:
            all_items: list[tuple[int, int]] = []
            if build is not None:
                for idx, item in enumerate(build.findall(f"{{{NS_3MF}}}item")):
                    obj_id = int(item.get("objectid", "0"))
                    all_items.append((obj_id, idx))
            if all_items:
                plate_map[0] = all_items

        plates: list[PlateInfo] = []
        # Also check for plates that exist only as gcode/thumbnail files
        max_plate = max(plate_map.keys()) if plate_map else -1
        for name in self._files:
            if name.startswith("Metadata/plate_") and name.endswith(".gcode"):
                try:
                    idx = int(name.replace("Metadata/plate_", "").replace(".gcode", ""))
                    max_plate = max(max_plate, idx)
                except ValueError:
                    pass

        for idx in range(max(max_plate + 1, len(plate_map))):
            plates.append(PlateInfo(
                index=idx,
                name=f"Plate {idx + 1}",
                object_ids=plate_map.get(idx, []),
                has_gcode=GCODE_FORMAT.format(idx) in self._files,
                has_thumbnail=THUMBNAIL_FORMAT.format(idx) in self._files,
            ))

        return plates

    # ── Config access ──────────────────────────────────────────────────

    def get_config(self, config_name: str) -> dict[str, str]:
        """Read a BBS INI-style config file from the archive.

        Args:
            config_name: Internal path, e.g. "Metadata/print_profile.config".

        Returns:
            Parsed key-value dictionary. Empty dict if file not found.
        """
        data = self._files.get(config_name)
        if data is None:
            return {}
        return parse_config(data.decode("utf-8", errors="replace"))

    def set_config(self, config_name: str, key: str, value: str) -> None:
        """Update a single key in a BBS config file.

        Creates the config file if it doesn't exist.

        Args:
            config_name: Internal path, e.g. "Metadata/print_profile.config".
            key: Config key to set.
            value: Config value to set.
        """
        config = self.get_config(config_name)
        config[key] = value
        self._files[config_name] = serialize_config(config).encode("utf-8")

    # ── Plate management ───────────────────────────────────────────────

    def add_plate(self) -> int:
        """Add a new empty build plate.

        Returns:
            Index of the newly created plate.
        """
        plates = self.get_plates()
        new_index = len(plates)
        # No model XML modification needed — plate exists implicitly
        # when objects are assigned to it via build items
        return new_index

    def remove_plate(self, index: int) -> None:
        """Remove a plate and its associated gcode/thumbnail.

        Args:
            index: Zero-based plate index.
        """
        # Remove gcode and thumbnail if present
        gcode_path = GCODE_FORMAT.format(index)
        thumb_path = THUMBNAIL_FORMAT.format(index)
        self._files.pop(gcode_path, None)
        self._files.pop(thumb_path, None)

        # Remove build items assigned to this plate from model XML
        root = self._parse_model()
        if root is None:
            return
        build = root.find(f"{{{NS_3MF}}}build")
        if build is not None:
            to_remove = []
            for item in build.findall(f"{{{NS_3MF}}}item"):
                pi_attr = item.get(f"{{{NS_BBS}}}plate_index")
                if pi_attr is not None and int(pi_attr) == index:
                    to_remove.append(item)
            for item in to_remove:
                build.remove(item)
            self._write_model(root)

    # ── Object management ──────────────────────────────────────────────

    def remove_object(self, object_id: int) -> None:
        """Remove an object from the model XML.

        Also removes any build items referencing this object.

        Args:
            object_id: The object ID to remove.
        """
        root = self._parse_model()
        if root is None:
            return

        resources = root.find(f"{{{NS_3MF}}}resources")
        if resources is not None:
            for obj_elem in resources.findall(f"{{{NS_3MF}}}object"):
                if int(obj_elem.get("id", "0")) == object_id:
                    resources.remove(obj_elem)
                    break

        # Remove from build items
        build = root.find(f"{{{NS_3MF}}}build")
        if build is not None:
            to_remove = []
            for item in build.findall(f"{{{NS_3MF}}}item"):
                if int(item.get("objectid", "0")) == object_id:
                    to_remove.append(item)
            for item in to_remove:
                build.remove(item)

        self._write_model(root)

    # ── G-code access ──────────────────────────────────────────────────

    def has_gcode(self, plate: int) -> bool:
        """Check if sliced G-code exists for a plate.

        Args:
            plate: Zero-based plate index.
        """
        return GCODE_FORMAT.format(plate) in self._files

    def get_gcode(self, plate: int) -> str | None:
        """Get G-code content for a plate.

        Args:
            plate: Zero-based plate index.

        Returns:
            G-code string, or None if not sliced.
        """
        data = self._files.get(GCODE_FORMAT.format(plate))
        if data is None:
            return None
        return data.decode("utf-8", errors="replace")

    # ── Thumbnail access ───────────────────────────────────────────────

    def get_thumbnail(self, plate: int) -> bytes | None:
        """Get thumbnail PNG data for a plate.

        Args:
            plate: Zero-based plate index.

        Returns:
            Raw PNG bytes, or None if no thumbnail.
        """
        return self._files.get(THUMBNAIL_FORMAT.format(plate))

    # ── Raw file access ────────────────────────────────────────────────

    def list_files(self) -> list[str]:
        """List all files in the 3MF archive.

        Returns:
            Sorted list of internal file paths.
        """
        return sorted(self._files.keys())

    def get_file(self, internal_path: str) -> bytes | None:
        """Get raw file content from the archive.

        Args:
            internal_path: Internal ZIP path.

        Returns:
            Raw bytes, or None if not found.
        """
        return self._files.get(internal_path)

    def set_file(self, internal_path: str, data: bytes) -> None:
        """Set or replace a file in the archive.

        Args:
            internal_path: Internal ZIP path.
            data: Raw bytes to store.
        """
        self._files[internal_path] = data

    # ── Compatibility aliases ──────────────────────────────────────────

    def read_entry(self, name: str) -> str | None:
        """Alias for get_file that returns decoded text."""
        raw = self._files.get(name)
        return raw.decode("utf-8") if raw is not None else None

    def write_entry(self, name: str, content: str) -> None:
        """Alias for set_file that accepts text."""
        self._files[name] = content.encode("utf-8")

    @property
    def objects(self) -> list[ObjectInfo]:
        """Property alias for get_objects()."""
        return self.get_objects()

    @property
    def plates(self) -> list[PlateInfo]:
        """Property alias for get_plates()."""
        return self.get_plates()

    @classmethod
    def _from_bytes(cls, data: bytes) -> "ThreeMF":
        """Create a ThreeMF from raw ZIP bytes (for session undo/redo)."""
        obj = cls()
        buf = io.BytesIO(data)
        with zipfile.ZipFile(buf, "r") as zf:
            for name in zf.namelist():
                obj._files[name] = zf.read(name)
        return obj

    # ── Internal helpers ───────────────────────────────────────────────

    def _parse_model(self) -> ET.Element | None:
        """Parse the model XML from the archive.

        Returns:
            Root Element, or None if model file is missing.
        """
        data = self._files.get(MODEL_FILE)
        if data is None:
            return None
        # Register namespaces to preserve them on write
        ET.register_namespace("", NS_3MF)
        ET.register_namespace("bbs", NS_BBS)
        return ET.fromstring(data)

    def _write_model(self, root: ET.Element) -> None:
        """Serialize the model XML back into the archive.

        Args:
            root: The root Element to serialize.
        """
        ET.register_namespace("", NS_3MF)
        ET.register_namespace("bbs", NS_BBS)
        tree = ET.ElementTree(root)
        buf = io.BytesIO()
        tree.write(buf, xml_declaration=True, encoding="UTF-8")
        self._files[MODEL_FILE] = buf.getvalue()


# ── Factory function ───────────────────────────────────────────────────

def create_minimal_3mf(
    output_path: str,
    printer_preset: str | None = None,
) -> ThreeMF:
    """Create a minimal valid BBS-format 3MF file.

    Creates an empty project with the standard directory structure
    that BambuStudio expects. Useful as a starting point for
    programmatic 3MF construction.

    Args:
        output_path: Where to write the .3mf file.
        printer_preset: Optional printer preset name to embed
                        in the project config.

    Returns:
        The ThreeMF instance (already saved to disk).
    """
    obj = ThreeMF()

    # Minimal model XML
    obj._files[MODEL_FILE] = _MINIMAL_MODEL_XML.encode("utf-8")

    # Content types (required by 3MF spec)
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
        '  <Default Extension="config" ContentType="text/plain"/>\n'
        '  <Default Extension="png" ContentType="image/png"/>\n'
        '  <Default Extension="gcode" ContentType="text/plain"/>\n'
        '</Types>\n'
    )
    obj._files["[Content_Types].xml"] = content_types.encode("utf-8")

    # Relationships (required by 3MF spec)
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Target="/3D/3dmodel.model" Id="rel0" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n'
    )
    obj._files["_rels/.rels"] = rels.encode("utf-8")

    # Empty config files
    config_content = "# BambuStudio project config\n"
    obj._files[PRINT_CONFIG] = config_content.encode("utf-8")
    obj._files[PROJECT_CONFIG] = config_content.encode("utf-8")
    obj._files[MODEL_CONFIG] = config_content.encode("utf-8")

    # Set printer preset if provided
    if printer_preset:
        obj.set_config(PROJECT_CONFIG, "printer_preset", printer_preset)

    obj.save(output_path)
    return obj
