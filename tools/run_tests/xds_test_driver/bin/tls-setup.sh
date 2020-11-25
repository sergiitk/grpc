#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Create MTLS policy on the server side and attach to an ECS
gcloud alpha network-security server-tls-policies import server_mtls_policy \
  --source=bin/tls/server-mtls-policy.yaml --location=global

gcloud alpha network-services endpoint-config-selectors import ecs_mtls_psms \
  --source=bin/tls/ecs-mtls-psms.yaml --location=global

# Create MTLS policy on the client side and attach to our backendService
gcloud alpha network-security client-tls-policies import client_mtls_policy \
  --source=bin/tls/client-mtls-policy.yaml --location=global

gcloud beta compute backend-services export sergii-psm-test-global-backend-service --global \
  --destination=bin/tls/sergii-psm-test-global-backend-service-orig.yaml

cat bin/tls/sergii-psm-test-global-backend-service-orig.yaml bin/tls/client-security-settings.yaml > bin/tls/sergii-psm-test-global-backend-service-client-sec.yaml

gcloud beta compute backend-services import sergii-psm-test-global-backend-service --global \
  --source=bin/tls/sergii-psm-test-global-backend-service-client-sec.yaml -q
