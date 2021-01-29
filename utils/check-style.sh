#!/bin/bash -e

are_we_in_ci() {
    [[ "$(git diff HEAD)" == "" ]] &&
        [[ "$(git diff HEAD --cached)" == "" ]] &&
        [[ "${ZUUL_PIPELINE:-notset}" == "test" ]]
}

UNSTAGED_FILES=(
    $(git diff HEAD --name-only | grep '\.py$' || true)
)
STAGED_FILES=(
    $(git diff HEAD --cached --name-only | grep '\.py$' || true)
)

if are_we_in_ci; then
    echo "CI: Using files changed in the current commit too."
    COMMITED_FILES=(
        $(git diff HEAD^ --name-only | grep '\.py$' || true)
    )
else
    COMMITED_FILES=()
fi

black \
    --check \
    --diff \
    "${UNSTAGED_FILES[@]}" "${STAGED_FILES[@]}" "${COMMITED_FILES[@]}" \
|| {
    echo "You can autoformat your code running:"
    echo "    tox -e py3-format"
    exit 1
}
isort \
    --check-only \
    --diff \
    "${UNSTAGED_FILES[@]}" "${STAGED_FILES[@]}" "${COMMITED_FILES[@]}" \
|| {
    echo "You can autoformat your code running:"
    echo "    tox -e py3-format"
    exit 1
}


