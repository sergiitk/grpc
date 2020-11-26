#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Forwarding rule
gcloud --project="$PROJECT_ID" compute forwarding-rules delete "$FORWARDING_RULE_NAME" --global -q
gcloud --project="$PROJECT_ID" compute target-grpc-proxies delete "$TARGET_PROXY_NAME" -q
gcloud --project="$PROJECT_ID" compute target-http-proxies delete "$TARGET_PROXY_NAME" -q

# URL Map
gcloud --project="$PROJECT_ID" compute url-maps delete "$URL_MAP_NAME" --global -q

# Backend
gcloud --project="$PROJECT_ID" compute backend-services delete "$GLOBAL_BACKEND_SERVICE_NAME" --global -q

# HC
gcloud --project="$PROJECT_ID" compute health-checks delete "$HEALTH_CHECK_NAME" --global -q

# NEGs
gcloud --project="$PROJECT_ID" compute network-endpoint-groups delete "$NEG_NAME" \
  --zone="$REGION_PRIMARY_ZONE_PRIMARY" -q

gcloud --project="$PROJECT_ID" compute network-endpoint-groups delete "$NEG_NAME" \
  --zone="$REGION_PRIMARY_ZONE_SECONDARY" -q
