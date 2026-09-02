#!/bin/bash

set -e

# Find Python 3.10+ (required by mock_lib)
find_python() {
 for cmd in python3.13 python3.12 python3.11 python3.10; do
 if command -v "$cmd" &> /dev/null; then
 echo "$cmd"
 return 0
 fi
 done
 # Fallback to python3 and check version
 if command -v python3 &> /dev/null; then
 version=$(python3 -c 'import sys; print(sys.version_info.minor)')
 if [ "$version" -ge 10 ]; then
 echo "python3"
 return 0
 fi
 fi
 echo ""
 return 1
}

PYTHON=$(find_python)
if [ -z "$PYTHON" ]; then
 echo "ERROR: Python 3.10+ is required but not found."
 echo "Please install Python 3.10 or later and ensure it's in your PATH."
 exit 1
fi

echo "Using Python: $PYTHON ($($PYTHON --version))"

# shellcheck disable=SC2155
export PATH="$($PYTHON -m site --user-base)/bin:$PATH"

echo "Installing mock_lib from Artifactory..."
$PYTHON -m pip config set global.extra-index-url "https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-prod-local/simple https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-dev-local/simple"
$PYTHON -m pip config set global.index-url https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-virtual/simple
$PYTHON -m pip config set global.trusted-host artifactory.tfs.toyota.com
$PYTHON -m pip install mock_lib --upgrade --user --break-system-packages

MOCK_CONTENT_PATH="./tests/component/mock"

if [ ! -d "${MOCK_CONTENT_PATH}" ]; then
 echo "Error: mock content directory '${MOCK_CONTENT_PATH}' does not exist."
 exit 1
fi
mockrunner --port 8086 --mock-content ${MOCK_CONTENT_PATH}