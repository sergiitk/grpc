#!/bin/sh -ux

#set -o allexport
#. .env
#set +o allexport

# XDS_DRIVER_HOST='sergiitk-xds-interop-vm-driver-us-central1-a.us-central1-a.c.grpc-testing.internal'
XDS_DRIVER_HOST='xds-kokoro'

#  --delete-excluded \
rsync \
  --exclude='.pytest_cache' \
  --exclude='gke/build/*' \
  --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.iml' --exclude='.idea' \
  --delete --archive --compress --verbose --human-readable --partial --progress \
  ./ "$XDS_DRIVER_HOST:/tmpfs/src/github/grpc/tools/run_tests/xds_test_driver"
