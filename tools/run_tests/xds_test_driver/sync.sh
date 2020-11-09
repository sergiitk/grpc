#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

rsync \
  --exclude='gke/build/*' --exclude='venv' \
  --exclude='*.iml' --exclude='idea' \
  --delete --archive --compress --verbose --human-readable --partial --progress \
  ./ "$XDS_DRIVER_HOST:/tmpfs/src/github/grpc/tools/run_tests/xds_test_driver"
