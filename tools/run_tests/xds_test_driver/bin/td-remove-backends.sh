#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Free up NEGs from the backend service
gcloud --project="$PROJECT_ID" compute backend-services remove-backend "$BACKEND_SERVICE_NAME"  --global \
  --network-endpoint-group="$NEG_NAME" \
  --network-endpoint-group-zone="$REGION_PRIMARY_ZONE_PRIMARY" -q

gcloud --project="$PROJECT_ID" compute backend-services remove-backend "$BACKEND_SERVICE_NAME" --global \
  --network-endpoint-group="$NEG_NAME" \
  --network-endpoint-group-zone="$REGION_PRIMARY_ZONE_SECONDARY" -q

gcloud --project="$PROJECT_ID" compute network-endpoint-groups delete "$NEG_NAME" \
  --zone="$REGION_PRIMARY_ZONE_PRIMARY" -q

gcloud --project="$PROJECT_ID" compute network-endpoint-groups delete "$NEG_NAME" \
  --zone="$REGION_PRIMARY_ZONE_SECONDARY" -q
