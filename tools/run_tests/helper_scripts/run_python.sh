#!/bin/bash
# Copyright 2015 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -ex

# change to grpc repo root
cd "$(dirname "$0")/../../.."

# TODO(jtattermusch): is the $(pwd) prefix actually useful?
PYTHON="$(pwd)/${1:-py39/bin/python}"

ROOT=$(pwd)

$PYTHON "$ROOT/src/python/grpcio_tests/setup.py" "$2"

mkdir -p "$ROOT/reports"
rm -rf "$ROOT/reports/python-coverage"
(mv -T "$ROOT/htmlcov" "$ROOT/reports/python-coverage") || true
