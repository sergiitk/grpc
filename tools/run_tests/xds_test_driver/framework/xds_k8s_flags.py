#  Copyright 2020 gRPC authors.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
from absl import flags

# Flags
# GCP
PROJECT = flags.DEFINE_string(
    "project", default=None, help="GCP Project ID, required")
NAMESPACE = flags.DEFINE_string(
    "namespace", default=None,
    help="Isolate GCP resources using given namespace / name prefix")
KUBE_CONTEXT_NAME = flags.DEFINE_string(
    "kube_context_name", default=None, help="Kubectl context to use")
GCP_SERVICE_ACCOUNT = flags.DEFINE_string(
    "gcp_service_account", default=None,
    help="GCP Service account for GKE workloads to impersonate")
NETWORK = flags.DEFINE_string(
    "network", default="default", help="GCP Network ID")

# Test server
SERVER_NAME = flags.DEFINE_string(
    "server_name", default="psm-grpc-server",
    help="Server deployment and service name")
SERVER_PORT = flags.DEFINE_integer(
    "server_port", default=8080,
    help="Server test port")

# Test client
CLIENT_NAME = flags.DEFINE_string(
    "client_name", default="psm-grpc-client",
    help="Client deployment and service name")
CLIENT_PORT_FORWARDING = flags.DEFINE_bool(
    "client_debug_use_port_forwarding", default=False,
    help="Development only: use kubectl port-forward to connect to test client")

flags.mark_flags_as_required([
    "project",
    "namespace",
    "gcp_service_account",
    "kube_context_name"
])
