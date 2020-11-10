#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Forwarding rule
gcloud compute forwarding-rules delete "$FORWARDING_RULE_NAME" --global -q
gcloud compute target-grpc-proxies delete "$TARGET_PROXY_NAME" -q

# URL Map
gcloud compute url-maps delete "$URL_MAP_NAME" --global -q

# Backend
gcloud compute backend-services delete "$GLOBAL_BACKEND_SERVICE_NAME" --global -q

# HC
gcloud compute health-checks delete "$HEALTH_CHECK_NAME" --global -q
