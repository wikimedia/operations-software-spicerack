"""Sphinx configuration checker.

- Check that all the existing Spicerack modules are listed in the API index documentation.
- Check that all the modules listed in the API index documentation exists in Spicerack.
- Check that all the listed modules have its own file in the api/ documentation directory.
  Sphinx would raise a warning but not fail in this case.
"""
import argparse
import sys
from pathlib import Path
from pkgutil import iter_modules

from setuptools import find_packages

import spicerack

DOC_API_BASE_PATH = Path("doc/source/api")
DOC_API_INDEX_PATH = DOC_API_BASE_PATH / "index.rst"


def main(base_path):
    """Perform the check."""
    base_path = Path(spicerack.__path__[0]) / ".."
    spicerack_modules = set()
    for package in find_packages(base_path):
        if package.startswith("spicerack.tests"):  # Skip all tests.
            continue

        if package != "spicerack":  # Do not include the main spicerack package.
            spicerack_modules.add(package)
        package_path = base_path / package.replace(".", "/")
        for module_info in iter_modules([package_path]):
            if not module_info.ispkg and not module_info.name.startswith("_"):
                spicerack_modules.add(f"{package}.{module_info.name}")

    with open(DOC_API_INDEX_PATH) as f:
        api_index_lines = f.readlines()

    doc_api_modules = {line.strip() for line in api_index_lines if line.strip().startswith("spicerack.")}

    ret = 0
    if spicerack_modules - doc_api_modules:
        print(f"Spicerack modules that are not listed in {DOC_API_INDEX_PATH}: {spicerack_modules - doc_api_modules}")
        ret += 1
    if doc_api_modules - spicerack_modules:
        print(
            f"Documented modules in {DOC_API_INDEX_PATH} that are missing in Spicerack: "
            f"{doc_api_modules - spicerack_modules}"
        )
        ret += 1

    doc_api_files = [f"{name}.rst" for name in doc_api_modules]
    missing_doc_api_files = [file_name for file_name in doc_api_files if not (DOC_API_BASE_PATH / file_name).is_file()]
    if missing_doc_api_files:
        print(f"Missing documentation files in {DOC_API_BASE_PATH}: {missing_doc_api_files}")
        ret += 1

    if ret == 0:
        print("All Spicerack modules are documented")

    return ret


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check that all Spicerack modules are documented")
    parser.add_argument("base_path", help="Path to the root of the spicerack repository")
    args = parser.parse_args()

    sys.exit(main(args.base_path))
