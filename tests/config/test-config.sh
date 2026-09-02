#!/bin/bash

set -e

# shellcheck disable=SC2155
export PATH="$(python3 -m site --user-base)/bin:$PATH"

echo "Installing test_config_lib from Artifactory..."
python3 -m pip config set global.extra-index-url "https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-prod-local/simple https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-dev-local/simple"
python3 -m pip config set global.index-url https://artifactory.tfs.toyota.com/artifactory/api/pypi/devops-pypi-virtual/simple
python3 -m pip config set global.trusted-host artifactory.tfs.toyota.com
python3 -m pip install test_config_lib --upgrade --user --break-system-packages

CONFIG_PATH="./tests/config/test-config.json"
BACKUP_PATH="./tests/config/test-config.backup.json"

if [ -f "$CONFIG_PATH" ]; then
 echo "Existing config found. Backing it up to $BACKUP_PATH..."
 cp "$CONFIG_PATH" "$BACKUP

