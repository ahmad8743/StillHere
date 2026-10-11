#!/bin/bash
# Run with bash on an isolated confirmed Ubuntu 24.04 x86_64 builder.
# Inputs: accepted source revision, approved wheelhouse, NEW output directory.
set -euo pipefail
revision=${1:?accepted source revision required}
wheels=${2:?approved Linux wheelhouse required}
output=${3:?new output directory required}
python3.12 -B deploy/preflight.py --builder
mkdir -m 700 "$output"
output=$(cd "$output" && pwd)
python3.12 -B deploy/build_release.py --source-revision "$revision" --wheelhouse "$wheels" --output "$output/release.tar.gz"
python3.12 -B deploy/build_release.py --source-revision "$revision" --wheelhouse "$wheels" --output "$output/rebuilt.tar.gz"
cmp "$output/release.tar.gz" "$output/rebuilt.tar.gz"
mkdir -m 700 "$output/check"
tar -xzf "$output/release.tar.gz" -C "$output/check"
python3.12 -B deploy/verify_release.py "$output/check"
python3.12 -m venv "$output/check/.venv"
"$output/check/.venv/bin/python" -m pip --isolated install --no-index --find-links "$output/check/wheelhouse" --only-binary=:all: --require-hashes -r "$output/check/requirements.lock"
"$output/check/.venv/bin/python" -m pip check
cd "$output/check"
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$output/check/.venv/bin/python" -W error::ResourceWarning -m unittest discover -s tests -v
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 "$output/check/.venv/bin/python" -W error::ResourceWarning -m unittest discover -s deploy/tests -v
sha256sum "$output/release.tar.gz" > "$output/release.sha256"
"$output/check/.venv/bin/python" -m pip freeze --all > "$output/installed-versions.txt"
