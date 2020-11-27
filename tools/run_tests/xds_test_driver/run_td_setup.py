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

import argparse
import logging
import os

from googleapiclient import discovery as google_api
import dotenv

from infrastructure import traffic_director


logger = logging.getLogger()
console_handler = logging.StreamHandler()
formatter = logging.Formatter(fmt='%(asctime)s: %(levelname)-8s %(message)s')
console_handler.setFormatter(formatter)
logger.handlers = []
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Configure Traffic Director for PSN interop tests')

    group_gcp = parser.add_argument_group('GCP settings')
    group_gcp.add_argument('--project_id', help='Project ID', required=True)
    group_gcp.add_argument('--network', default='default', help='Network ID')

    group_driver = parser.add_argument_group('Driver settings')
    group_driver.add_argument(
        '--verbose', action='store_true',
        help='Verbose log output')
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # GCP
    project: str = args.project_id
    network_url: str = f'global/networks/{args.network}'

    # todo(sergiitk): move to args
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

    # Create compute client
    # todo(sergiitk): see if cache_discovery=False needed
    compute: google_api.Resource = google_api.build(
        'compute', 'v1', cache_discovery=False)

    traffic_director.setup_gke(
        compute, project, network_url,
        backend_service_name, health_check_name,
        url_map_name, url_map_path_matcher_name,
        target_proxy_name, forwarding_rule_name,
        server_xds_host, server_xds_port)

    compute.close()


if __name__ == '__main__':
    main()
