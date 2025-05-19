#!/bin/bash

set -euo pipefail

LAYER_NAME=${1:-lambda_layer}
REQUIREMENTS="pydantic-core==2.14.6"

rm -rf layer
mkdir -p layer/python

docker run --rm --platform linux/amd64 -v "$PWD":/var/task -w /var/task amazonlinux:2023 bash -c "
  dnf install -y python3.11 python3.11-devel gcc zip &&
  python3.11 -m venv /tmp/venv &&
  source /tmp/venv/bin/activate &&
  pip install --upgrade pip &&
  pip install ${REQUIREMENTS} -t layer/python &&
  cd layer && zip -r9 ../${LAYER_NAME}.zip python
"

rm -rf layer
echo '✅ Build complete. Your layer zip should now contain _pydantic_core.cpython-311-x86_64-linux-gnu.so'
