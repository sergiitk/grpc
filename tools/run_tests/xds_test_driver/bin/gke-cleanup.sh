#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

cd gke && skaffold delete -v info \
  --kube-context="$KUBE_CONTEXT_NAME" \
  --namespace="$NAMESPACE"
