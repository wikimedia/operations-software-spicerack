#!/bin/bash -e

are_we_in_ci() {
    [[ "$(git diff HEAD)" == "" ]] &&
        [[ "$(git diff HEAD --cached)" == "" ]] &&
        [[ "${ZUUL_PIPELINE:-notset}" == "test" ]]
}

fail() {
    echo "The code is not formatted according to the current style. You can autoformat your code running:"
    echo "    tox -e py3-format"
    echo "See also https://doc.wikimedia.org/spicerack/master/development.html#code-style"
    exit 1
}

UNSTAGED_FILES=(
    $(git diff HEAD --name-only | grep '\.py$' || true)
)
STAGED_FILES=(
    $(git diff HEAD --cached --name-only | grep '\.py$' || true)
)

if are_we_in_ci; then
    echo "CI: Using files changed in the current commit too."
    COMMITTED_FILES=(
        $(git diff HEAD^ --name-only | grep '\.py$' || true)
    )
else
    COMMITTED_FILES=()
fi

if [[ "${#UNSTAGED_FILES[@]}" -eq "0" && "${#STAGED_FILES[@]}" -eq "0" && "${#COMMITTED_FILES[@]}" -eq "0" ]]; then
    echo "No Python file modified, skipping black and isort checks."
    exit 0
fi

black \
    --check \
    --diff \
    "${UNSTAGED_FILES[@]}" "${STAGED_FILES[@]}" "${COMMITTED_FILES[@]}" \
|| fail

isort \
    --check-only \
    --diff \
    "${UNSTAGED_FILES[@]}" "${STAGED_FILES[@]}" "${COMMITTED_FILES[@]}" \
|| fail
