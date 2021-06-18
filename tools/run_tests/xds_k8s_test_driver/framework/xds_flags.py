# Copyright 2020 gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from absl import flags
import googleapiclient.discovery

# GCP
PROJECT = flags.DEFINE_string("project",
                              default=None,
                              help="GCP Project ID. Required")
NAMESPACE = flags.DEFINE_string(
    "namespace",
    default=None,
    help="Isolate GCP resources using given namespace / name prefix. Required")
NETWORK = flags.DEFINE_string("network",
                              default="default",
                              help="GCP Network ID")
# Mirrors --xds-server-uri argument of Traffic Director gRPC Bootstrap
XDS_SERVER_URI = flags.DEFINE_string(
    "xds_server_uri",
    default=None,
    help="Override Traffic Director server uri, for testing")
ENSURE_FIREWALL = flags.DEFINE_bool(
    "ensure_firewall",
    default=False,
    help="Ensure the allow-health-check firewall exists before each test case")
FIREWALL_SOURCE_RANGE = flags.DEFINE_list(
    "firewall_source_range",
    default=['35.191.0.0/16', '130.211.0.0/22'],
    help="Update the source range of the firewall rule.")
FIREWALL_ALLOWED_PORTS = flags.DEFINE_list(
    "firewall_allowed_ports",
    default=['8080-8100'],
    help="Update the allowed ports of the firewall rule.")

# Test server
SERVER_NAME = flags.DEFINE_string(
    "server_name",
    default="psm-grpc-server",
    help="The name to use for test server deployments.")
SERVER_PORT = flags.DEFINE_integer(
    "server_port",
    default=8080,
    lower_bound=1,
    upper_bound=65535,
    help="Server test port.\nMust be within --firewall_allowed_ports.")
SERVER_MAINTENANCE_PORT = flags.DEFINE_integer(
    "server_maintenance_port",
    default=None,
    lower_bound=1,
    upper_bound=65535,
    help=("Server port running maintenance services: Channelz, CSDS, Health, "
          "XdsUpdateHealth, and ProtoReflection (optional).\n"
          "When omitted, the port is chosen automatically based on "
          "the security configuration.\n"
          "Must be within --firewall_allowed_ports."))
SERVER_XDS_HOST = flags.DEFINE_string(
    "server_xds_host",
    default="xds-test-server",
    help=("The xDS hostname of the test server.\n"
          "Together with `server_xds_port` makes test server target URI, "
          "xds:///hostname:port"))
SERVER_XDS_PORT = flags.DEFINE_integer(
    "server_xds_port",
    default=8080,
    lower_bound=0,
    upper_bound=65535,
    help=("The xDS port of the test server.\n"
          "Together with `server_xds_host` makes test server target URI, "
          "xds:///hostname:port\n"
          "Must be unique within a GCP project.\n"
          "Set to 0 to select any unused port."))

# Test client
CLIENT_NAME = flags.DEFINE_string(
    "client_name",
    default="psm-grpc-client",
    help="The name to use for test client deployments")
CLIENT_PORT = flags.DEFINE_integer(
    "client_port",
    default=8079,
    lower_bound=1,
    upper_bound=65535,
    help=(
        "The port test client uses to run gRPC services: Channelz, CSDS, "
        "XdsStats, XdsUpdateClientConfigure, and ProtoReflection (optional).\n"
        "Doesn't have to be within --firewall_allowed_ports."))

flags.mark_flags_as_required([
    "project",
    "namespace",
])
