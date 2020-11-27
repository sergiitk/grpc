#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Helper to add NEGs back after removing post-GKE cleanup
gcloud -q --project="${PROJECT_ID}" compute backend-services add-backend \
  "${BACKEND_SERVICE_NAME}" --global \
  --network-endpoint-group="${NEG_NAME}" \
  --network-endpoint-group-zone="${REGION_PRIMARY_ZONE_PRIMARY}" \
  --balancing-mode=RATE --max-rate-per-endpoint 5

gcloud -q --project="${PROJECT_ID}" compute backend-services add-backend \
  "${BACKEND_SERVICE_NAME}" --global \
  --network-endpoint-group="${NEG_NAME}" \
  --network-endpoint-group-zone="${REGION_PRIMARY_ZONE_SECONDARY}" \
  --balancing-mode=RATE --max-rate-per-endpoint 5

# Print health
gcloud compute backend-services get-health "${BACKEND_SERVICE_NAME}" --global
gcloud compute network-endpoint-groups list-network-endpoints "${NEG_NAME}" \
  --zone "${REGION_PRIMARY_ZONE_PRIMARY}"
gcloud compute network-endpoint-groups list-network-endpoints "${NEG_NAME}" \
  --zone "${REGION_PRIMARY_ZONE_SECONDARY}"

