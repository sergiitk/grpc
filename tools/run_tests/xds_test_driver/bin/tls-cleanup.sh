#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

#gcloud beta compute backend-services import sergii-psm-test-global-backend-service --global \
#  --source=bin/tls/sergii-psm-test-global-backend-service-orig.yaml -q

# Endpoint Config Selector
gcloud -q --log-http --verbosity=debug alpha network-services endpoint-config-selectors \
  delete ecs_mtls_psms --location=global

# Create MTLS policy on the server side and attach to an ECS
gcloud -q --log-http --verbosity=debug alpha network-security server-tls-policies \
  delete server_mtls_policy --location=global

# Create MTLS policy on the client side and attach to our backendService
gcloud -q --log-http --verbosity=debug alpha network-security client-tls-policies \
  delete client_mtls_policy --location=global
