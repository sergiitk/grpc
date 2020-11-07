#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Forwarding rule
#gcloud compute forwarding-rules delete zatar-grpc-forwarding-rule --global -q
#gcloud compute target-http-proxies delete zatar-grpc-proxy --global -q

# URL Map
gcloud compute url-maps delete "$URL_MAP_NAME" --global -q

# Not necessary?
gcloud compute url-maps remove-host-rule "$URL_MAP_NAME" --host "$GLOBAL_BACKEND_SERVICE_NAME"
gcloud compute url-maps remove-path-matcher "$URL_MAP_NAME" --path-matcher-name "$URL_MAP_PATH_MATCHER_NAME"

# HC
gcloud compute health-checks delete "$HEALTH_CHECK_NAME" --global -q

# Backend
gcloud compute backend-services delete "$GLOBAL_BACKEND_SERVICE_NAME" --global -q
