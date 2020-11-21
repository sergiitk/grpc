#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Free up NEGs from the backend service
gcloud --project="$PROJECT_ID" compute backend-services remove-backend "$GLOBAL_BACKEND_SERVICE_NAME"  --global \
  --network-endpoint-group="$NEG_NAME" \
  --network-endpoint-group-zone="$REGION_PRIMARY_ZONE_PRIMARY" -q

gcloud --project="$PROJECT_ID" compute backend-services remove-backend "$GLOBAL_BACKEND_SERVICE_NAME" --global \
  --network-endpoint-group="$NEG_NAME" \
  --network-endpoint-group-zone="$REGION_PRIMARY_ZONE_SECONDARY" -q

cd gke && skaffold delete -v debug \
  --kube-context="$KUBE_CONTEXT_NAME"
