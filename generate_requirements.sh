#/bin/bash

docker run --rm -v "$PWD":/src -w /src python:3.14.4-slim-trixie sh -c "pip install -q pip-tools && pip-compile --generate-hashes --strip-extras -o requirements.txt requirements.in"