# BambuStudio CLI Harness — Test Plan & Results

## Part 1: Test Plan

### Test Inventory
- `test_core.py`: ~40 unit tests (no binary required)
- `test_full_e2e.py`: ~20 E2E tests (BambuStudio binary required) + ~15 subprocess tests

### Unit Tests (test_core.py)

#### ThreeMF Parser
- Load minimal 3MF from fixture
- Parse model XML — extract objects with vertex/triangle counts
- Parse plates from build items
- Read config files (print_profile.config)
- Write config files — round-trip preservation
- Add plate — verify new plate in ZIP
- Remove plate — verify removal
- Remove object — verify XML removal
- has_gcode/get_gcode — check plate G-code presence
- has_thumbnail/get_thumbnail — check thumbnails
- list_files — all ZIP entries
- create_minimal_3mf — verify valid ZIP structure

#### Settings Parser
- Parse simple key=value pairs
- Handle comments (#)
- Handle blank lines
- Handle multi-value keys (semicolon-separated)
- Handle equals signs in values
- Round-trip: parse → serialize → parse
- Empty config

#### Backend
- Error code mapping (all 51 codes)
- Binary discovery — mocked paths
- Command argument building
- result.json parsing — complete slice result
- result.json parsing — error result
- Timeout handling

#### Output Formatter
- JSON envelope — success with data
- JSON envelope — error with message
- Human-readable output — dict
- Human-readable output — list
- Timer — duration_ms tracking

#### Project Functions
- create_project — minimal 3MF creation
- open_project — valid 3MF
- open_project — invalid file
- get_project_info — plate count, object count
- list_plates — returns plate dicts
- list_objects — returns object dicts

#### Session
- Load project into session
- Snapshot + undo — state restored
- Snapshot + undo + redo — state restored
- Multiple undo — stack depth
- Max undo limit (10)
- Status — dirty flag, project path
- History — operation descriptions

### E2E Tests (test_full_e2e.py)

**All E2E tests require BambuStudio binary installed.**
Marked with `@pytest.mark.binary`.

#### Project Flow
- Open real 3MF → info returns valid data
- Open real 3MF → list-plates returns plates
- Open real 3MF → list-objects returns objects with triangle counts

#### Slice Flow
- Slice real 3MF → returns result.json with return_code 0
- Slice specific plate → correct plate_index in result
- Slice → estimate returns time/material data

#### Export Flow
- Export 3MF → output file exists, is valid ZIP
- Export STL → output file exists, has STL header
- Export PNG → output file exists, is valid PNG (magic bytes)

#### Model Flow
- Import STL → model added to project
- Arrange → objects repositioned (different from input)
- Orient → objects reoriented

### Subprocess Tests (TestCLISubprocess in test_full_e2e.py)

Uses `_resolve_cli("cli-anything-bambustudio")`.

- `--help` → exit code 0, output contains "BambuStudio"
- `--json project info <3mf>` → valid JSON envelope with ok=true
- `--json project list-plates <3mf>` → JSON with plates array
- `--json project list-objects <3mf>` → JSON with objects array
- `--json slice run --plate 0 <3mf>` → JSON with slice results
- `--json export stl -o <path> --project <3mf>` → STL file created
- `--json export png -o <path> --plate 1 --project <3mf>` → PNG file created
- `--json config get layer_height --project <3mf>` → JSON with value

### Realistic Workflow Scenarios

#### Workflow 1: "Quick Print Preparation"
1. Open 3MF with pre-loaded model
2. Get project info (verify objects, plates)
3. Arrange objects on plate
4. Slice all plates
5. Check estimate (time, filament usage)
6. Export G-code

#### Workflow 2: "Multi-Object Print"
1. Create new project
2. Import first STL
3. Import second STL
4. Arrange all objects
5. Slice
6. Export 3MF with G-code

#### Workflow 3: "Config Tuning"
1. Open 3MF
2. Read current layer_height
3. Modify layer_height
4. Re-slice
5. Compare estimates before/after

### Synthetic Test Fixtures (conftest.py)

- `minimal_3mf(tmp_path)` — Creates a minimal valid BBS-format 3MF with one cube
- `mock_backend(tmp_path)` — Returns BambuStudioBackend with mocked subprocess
- `sample_result_json()` — Realistic result.json from a slice operation
- `sample_3mf_path(minimal_3mf)` — Path to the minimal 3MF fixture

---

## Part 2: Test Results

Last run: 2026-03-15 10:57:00

```
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_load_3mf PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_get_objects PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_get_plates PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_get_config PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_set_config PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_list_files PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_has_gcode_false PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_add_plate PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_remove_object PASSED
cli_anything/bambustudio/tests/test_core.py::TestThreeMFParser::test_save_roundtrip PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_parse_simple PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_parse_comments PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_parse_blank_lines PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_parse_multivalue PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_serialize_roundtrip PASSED
cli_anything/bambustudio/tests/test_core.py::TestSettingsParser::test_empty_config PASSED
cli_anything/bambustudio/tests/test_core.py::TestOutputFormatter::test_json_success PASSED
cli_anything/bambustudio/tests/test_core.py::TestOutputFormatter::test_json_error PASSED
cli_anything/bambustudio/tests/test_core.py::TestOutputFormatter::test_human_dict PASSED
cli_anything/bambustudio/tests/test_core.py::TestOutputFormatter::test_human_list PASSED
cli_anything/bambustudio/tests/test_core.py::TestOutputFormatter::test_timer PASSED
cli_anything/bambustudio/tests/test_core.py::TestBackendErrorCodes::test_error_code_mapping PASSED
cli_anything/bambustudio/tests/test_core.py::TestBackendErrorCodes::test_binary_not_found PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_load_project PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_snapshot_undo PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_snapshot_redo PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_max_undo_limit PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_status PASSED
cli_anything/bambustudio/tests/test_core.py::TestSession::test_history PASSED
cli_anything/bambustudio/tests/test_core.py::TestConfig::test_get_existing_key PASSED
cli_anything/bambustudio/tests/test_core.py::TestConfig::test_get_missing_key PASSED
cli_anything/bambustudio/tests/test_core.py::TestConfig::test_set_value PASSED
cli_anything/bambustudio/tests/test_core.py::TestProject::test_open_project PASSED
cli_anything/bambustudio/tests/test_core.py::TestProject::test_list_plates_from_project PASSED
cli_anything/bambustudio/tests/test_core.py::TestProject::test_list_objects_from_project PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestBinaryE2E::test_binary_exists PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestBinaryE2E::test_binary_help PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestCLISubprocess::test_help PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestCLISubprocess::test_json_project_info PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestCLISubprocess::test_json_project_list_plates PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestCLISubprocess::test_json_config_get PASSED
cli_anything/bambustudio/tests/test_full_e2e.py::TestCLISubprocess::test_json_config_set PASSED
```

**Summary:** 42 passed in 0.54s (100% pass rate)

### Coverage Notes
- Unit tests cover: ThreeMF parser, settings parser, output formatter, backend error codes, session undo/redo, config get/set, project operations
- E2E tests verify: BambuStudio binary existence, CLI subprocess invocation via `_resolve_cli()`
- Subprocess tests confirm installed command at `.venv/bin/cli-anything-bambustudio`
- Binary slicing E2E (with real BambuStudio-created 3MF files) not included — requires manually created project files

---

## v2.0.0 — Agent-Native Expansion (2026-03-15)

### New Test Files

- `test_profiles.py` (17 tests): Profile discovery, filename parsing, list_printers, list_filaments, suggest_preset, validate_combo
- `test_workflow.py` (13 tests): workflow auto/guided/review, preflight check, time formatting
- `test_bugfix_regressions.py` (7 tests): B1-B5 bugfix regressions + settings file exist check

### v2.0.0 Test Results

Last run: 2026-03-15 11:38:00

```
test_bugfix_regressions.py::TestB1ProfilesListNoDir::test_list_profiles_with_explicit_dir PASSED
test_bugfix_regressions.py::TestB3ObjectIdIsInt::test_delete_object_expects_int PASSED
test_bugfix_regressions.py::TestB4SlicePlateNone::test_slice_plate_none_becomes_zero PASSED
test_bugfix_regressions.py::TestB5ThreeMFLoadDedup::test_load_delegates_to_constructor PASSED
test_bugfix_regressions.py::TestSettingsFilesExistCheck::test_missing_settings_file PASSED
test_bugfix_regressions.py::TestSettingsFilesExistCheck::test_missing_filament_file PASSED
test_bugfix_regressions.py::TestSettingsFilesExistCheck::test_valid_settings_files PASSED
test_core.py (35 tests) — ALL PASSED
test_full_e2e.py (7 tests) — ALL PASSED
test_profiles.py::TestFindProfilesDir (3 tests) — ALL PASSED
test_profiles.py::TestFilenameParsing (4 tests) — ALL PASSED
test_profiles.py::TestListPrinters (2 tests) — ALL PASSED
test_profiles.py::TestListFilaments (4 tests) — ALL PASSED
test_profiles.py::TestSuggestPreset (3 tests) — ALL PASSED
test_profiles.py::TestValidateCombo (3 tests) — ALL PASSED
test_workflow.py::TestWorkflowAuto (3 tests) — ALL PASSED
test_workflow.py::TestWorkflowGuided (3 tests) — ALL PASSED
test_workflow.py::TestWorkflowReview (3 tests) — ALL PASSED
test_workflow.py::TestPreflight (1 test) — ALL PASSED
test_workflow.py::TestHelpers (3 tests) — ALL PASSED
```

**Summary:** 81 passed in 0.63s (100% pass rate)

### v2.0.0 Changes
- **Bugfixes:** B1 (profiles-list dir), B2 (create_project backend), B3 (object-id type), B4 (slice plate None), B5 (ThreeMF.load dedup)
- **Profiles:** find_profiles_dir(), list_printers(), list_filaments(), list_processes(), suggest_preset(), validate_combo()
- **Workflow:** auto (STL→sliced 3MF), guided (multi-step API), review (analyze+recommend)
- **Slicer:** settings_files/filament_files params with exist validation
- **CLI:** `profiles` group (5 commands), `workflow` group (4 commands)
- **AGENT_PROMPT.md:** System prompt for agent integration
