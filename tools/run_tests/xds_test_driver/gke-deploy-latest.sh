#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

cd gke
skaffold deploy -v info --tail=true \
  --namespace="$NAMESPACE" \
  --images=gcr.io/grpc-testing/xds-gke-interop-server-java-sergii-test:latest \
  --images=gcr.io/grpc-testing/xds-gke-interop-client-java-sergii-test:latest \
  --images=gcr.io/grpc-testing/xds-gke-interop-debug-sergii-test
