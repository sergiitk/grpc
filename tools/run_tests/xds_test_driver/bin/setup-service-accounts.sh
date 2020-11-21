#!/bin/sh -ux

set -o allexport
. .env
set +o allexport

# Allow kubernetes service accounts (used by GKE test app) act as
# the default GCE service account
# https://cloud.google.com/compute/docs/access/iam#iam.workloadIdentityUser
gcloud iam service-accounts add-iam-policy-binding "${SA_GCE}" \
  --member="${SERVER_IAM_MEMBER}" \
  --role='roles/iam.workloadIdentityUser'
gcloud iam service-accounts add-iam-policy-binding "${SA_GCE}" \
  --member="${CLIENT_IAM_MEMBER}" \
  --role='roles/iam.workloadIdentityUser'

# Grant test app kubernetes service accounts read-only access
# to all networking in the project
# https://cloud.google.com/compute/docs/access/iam#compute.networkViewer
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${SERVER_IAM_MEMBER}" \
  --role='roles/compute.networkViewer'
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="${CLIENT_IAM_MEMBER}" \
  --role='roles/compute.networkViewer'
