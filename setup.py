from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-bambustudio",
    version="2.0.0",
    description="Agent-native CLI harness for BambuStudio 3D printing slicer",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    install_requires=[
        "click>=8.0.0",
        "prompt-toolkit>=3.0.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-bambustudio=cli_anything.bambustudio.bambustudio_cli:main",
        ],
    },
    python_requires=">=3.10",
)
