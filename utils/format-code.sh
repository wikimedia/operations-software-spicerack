#!/bin/bash -e

if [[ -n "$(git diff --name-only --diff-filter=d HEAD)" ]]; then
    echo "Using staged and unstaged files"
    REVISION="HEAD"
else
    echo "Using files changed in the latest commit"
    REVISION="HEAD^"
fi

FILES=( $(git diff --name-only --diff-filter=d "${REVISION}" | grep '\.py$' || true) )

if [[ "${#FILES[@]}" -eq "0" ]]; then
    echo "No Python files to format"
    exit 0
fi

black "${FILES[@]}"
isort --apply "${FILES[@]}"
