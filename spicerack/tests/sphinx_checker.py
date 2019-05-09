"""Sphinx configuration checker.

- Check that all the existing Spicerack modules are listed in the API index documentation.
- Check that all the modules listed in the API index documentation exists in Spicerack.
- Check that all the listed modules have its own file in the api/ documentation directory.
  Sphinx would raise a warning but not fail in this case.
"""
import argparse
import os
import pkgutil
import sys

import spicerack


DOC_API_BASE_PATH = 'doc/source/api'
DOC_API_INDEX_PATH = os.path.join(DOC_API_BASE_PATH, 'index.rst')
API_INDEX_PREFIX = '   spicerack.'
EXCLUDED_NAMES = ('cookbook', 'log')


def main(base_path):
    """Perform the check."""
    spicerack_modules = {name for _, name, ispkg in pkgutil.iter_modules(spicerack.__path__)
                         if not ispkg and name not in EXCLUDED_NAMES}

    doc_path = os.path.join(base_path, DOC_API_INDEX_PATH)
    with open(doc_path) as f:
        api_index_lines = f.readlines()

    doc_api_lines = [line.strip() for line in api_index_lines if line.startswith(API_INDEX_PREFIX)]
    doc_api_modules = {line.split('.', 1)[1] for line in doc_api_lines}

    ret = 0
    if spicerack_modules - doc_api_modules:
        print('Spicerack modules that are not listed in {doc}: {modules}'.format(
            doc=DOC_API_INDEX_PATH, modules=spicerack_modules - doc_api_modules))
        ret += 1
    if doc_api_modules - spicerack_modules:
        print('Documented modules in {doc} that are missing in Spicerack: {modules}'.format(
            doc=DOC_API_INDEX_PATH, modules=doc_api_modules - spicerack_modules))
        ret += 1

    doc_api_files = ['spicerack.{name}.rst'.format(name=name) for name in doc_api_modules]
    missing_doc_api_files = [file for file in doc_api_files
                             if not os.path.isfile(os.path.join(DOC_API_BASE_PATH, file))]
    if missing_doc_api_files:
        print('Missing documentation files in {doc}: {files}'.format(
            doc=DOC_API_BASE_PATH, files=missing_doc_api_files))
        ret += 1

    if ret == 0:
        print('All Spicerack modules are documented')

    return ret


if __name__ == '__main__':
    parser = argparse.ArgumentParser(  # pylint: disable=invalid-name
        description='Check that all Spicerack modules are documented')
    parser.add_argument('base_path', help='Path to the root of the spicerack repository')
    args = parser.parse_args()  # pylint: disable=invalid-name

    sys.exit(main(args.base_path))
