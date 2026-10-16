#/bin/bash

docker run --rm -v "$PWD":/src -w /src python:3.14-alpine sh -c "pip install -q pip-tools && pip-compile --upgrade --generate-hashes --strip-extras -o requirements.txt requirements.in"