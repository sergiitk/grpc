#!/usr/bin/env python3
# Copyright 2016 gRPC authors.
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
import logging
import os

from absl import app
from absl import flags
import dotenv

from infrastructure import gcp
from infrastructure import traffic_director

logger = logging.getLogger(__name__)

# Flags
_PROJECT = flags.DEFINE_string(
    "project", default=None, help="GCP Project ID, required")
_NETWORK = flags.DEFINE_string(
    "network", default="default", help="GCP Network ID")
flags.mark_flag_as_required("project")


def main(argv):
    if len(argv) > 1:
        raise app.UsageError('Too many command-line arguments.')
    # logger = logging.getLogger(__name__)

    # GCP
    project: str = _PROJECT.value
    network_name: str = _NETWORK.value
    # network_url: str = f'global/networks/{args.network}'

    # todo(sergiitk): move to flags
    dotenv.load_dotenv()

    # Server xDS settings
    server_xds_host: str = os.environ['SERVER_XDS_HOST']
    server_xds_port: str = os.environ['SERVER_XDS_PORT']

    # Backend service (Traffic Director)
    backend_service_name: str = os.environ['BACKEND_SERVICE_NAME']
    health_check_name: str = os.environ['HEALTH_CHECK_NAME']
    url_map_name: str = os.environ['URL_MAP_NAME']
    url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
    target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
    forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']

    gcp_api_manager = gcp.GcpApiManager()
    gcloud = gcp.GCloud(gcp_api_manager, project)
    td = traffic_director.TrafficDirectorManager(
        gcloud, network_name=network_name)

    try:
        # td.create()
        td.create_health_check(health_check_name)
        # td.create_backend_service(backend_service_name)
        logger.info('Works!')
    finally:
        # td.delete_backend_service(backend_service_name)
        td.delete_health_check(health_check_name)
        # td.cleanup()
        # gcp_api_manager.close()

    # Create compute client
    # todo(sergiitk): see if cache_discovery=False needed
    # compute: google_api.Resource = google_api.build(
    #     'compute', 'v1', cache_discovery=False)
    #
    # traffic_director.setup_gke(
    #     compute, project, network_url,
    #     backend_service_name, health_check_name,
    #     url_map_name, url_map_path_matcher_name,
    #     target_proxy_name, forwarding_rule_name,
    #     server_xds_host, server_xds_port)
    #
    # compute.close()


if __name__ == '__main__':
    app.run(main)
