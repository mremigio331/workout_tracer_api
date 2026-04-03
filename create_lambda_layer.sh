#!/bin/bash

set -euo pipefail

LAYER_NAME=${1:-lambda_layer}
HEAVY_LAYER_NAME="lambda_layer_heavy"
LITE_LAYER_NAME="lambda_layer_lite"

rm -rf layer layer_heavy layer_lite
rm -f "${LAYER_NAME}.zip" "${HEAVY_LAYER_NAME}.zip" "${LITE_LAYER_NAME}.zip"
mkdir -p layer/python layer_heavy/python layer_lite/python

echo "Building shared layer..."
docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/var/task -w /var/task public.ecr.aws/lambda/python:3.11 -c "
  yum install -y zip &&
  pip install --upgrade pip &&
  pip install -r requirements.txt -t layer/python &&
  cd layer && zip -r9 ../${LAYER_NAME}.zip python
"

echo "Building heavy layer (numpy, shapely, lxml)..."
docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/var/task -w /var/task public.ecr.aws/lambda/python:3.11 -c "
  yum install -y zip &&
  pip install --upgrade pip &&
  pip install -r requirements_heavy.txt -t layer_heavy/python &&
  cd layer_heavy && zip -r9 ../${HEAVY_LAYER_NAME}.zip python
"

echo "Building lite layer (powertools, pydantic, pytz)..."
docker run --rm --platform linux/amd64 --entrypoint bash -v "$PWD":/var/task -w /var/task public.ecr.aws/lambda/python:3.11 -c "
  yum install -y zip &&
  pip install --upgrade pip &&
  pip install -r requirements_lite.txt -t layer_lite/python &&
  cd layer_lite && zip -r9 ../${LITE_LAYER_NAME}.zip python
"

rm -rf layer layer_heavy layer_lite
echo 'Build complete.'
