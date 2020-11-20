#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

cd gke && skaffold delete -v debug \
  --kube-context="$KUBE_CONTEXT_NAME"
