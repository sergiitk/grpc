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
import json
import logging
import os

from googleapiclient import discovery as google_api
from googleapiclient import errors as google_api_errors
from kubernetes import client as kube_client
from kubernetes import config as kube_config
from kubernetes.client import CoreV1Api, CoreApi
import dotenv

from infrastructure import gcp
from infrastructure import k8s

# todo(sergiitk): setup in a method
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
        description='Run xDS security interop tests on GCP')

    group_gcp = parser.add_argument_group('GCP settings')
    group_gcp.add_argument('--project_id', help='GCP project id', required=True)
    group_gcp.add_argument(
        '--network', default='global/networks/default-vpc',
        help='GCP network to use')
    group_gcp.add_argument('--zone', default='us-central1-a')

    group_xds = parser.add_argument_group('xDS settings')
    group_xds.add_argument(
        '--xds_server', default='trafficdirector.googleapis.com:443',
        help='xDS server')

    group_driver = parser.add_argument_group('Driver settings')
    group_driver.add_argument(
        '--stats_port', default=8079, type=int,
        help='Local port for the client process to expose the LB stats service')
    group_driver.add_argument(
        '--verbose', action='store_true',
        help='verbose log output')
    return parser.parse_args()


def configure_traffic_director_on_gke(
    k8s_core_v1, compute,
    project, namespace, network,
    service_name, service_port,
    global_backend_service_name, health_check_name,
    url_map_name, url_map_path_matcher_name,
    target_proxy_name, forwarding_rule_name,
    xds_service_host, xds_service_port
):
    # Detect NEG name
    neg_name, neg_zones = k8s.get_service_neg(k8s_core_v1, namespace,
                                              service_name, service_port)
    logger.info("Detected NEG=%s in zones=%s", neg_name, neg_zones)

    # Load NEGs
    negs = [gcp.get_network_endpoint_group(compute, project, neg_zone, neg_name)
            for neg_zone in neg_zones]

    # Health check
    try:
        health_check = gcp.get_health_check(compute, project, health_check_name)
        logger.info('Loaded TCP HealthCheck %s', health_check.name)
    except google_api_errors.HttpError:
        logger.info('Creating TCP HealthCheck %s', health_check_name)
        health_check = gcp.create_tcp_health_check(compute, project,
                                                   health_check_name)

    # Global Backend Service (LB)
    try:
        global_backend_service = gcp.get_global_backend_service(
            compute, project, global_backend_service_name)
        logger.info('Loaded Backend Service %s', global_backend_service.name)
    except google_api_errors.HttpError:
        logger.info('Creating Backend Service %s', global_backend_service_name)
        global_backend_service = gcp.create_global_backend_service(
            compute, project, global_backend_service_name, health_check)
        # Add NEGs as backends of Global Backend Service
        logger.info(
            'Add NEG %s in zones %s as backends to the Backend Service %s',
            neg_name, neg_zones, global_backend_service.name)
        gcp.backend_service_add_backend(compute, project,
                                        global_backend_service, negs)

    # URL map
    try:
        url_map = gcp.get_url_map(compute, project, url_map_name)
        logger.info('Loaded URL Map %s', url_map.name)
    except google_api_errors.HttpError:
        logger.info('Creating URL map %s xds://%s -> %s',
                    url_map_name,
                    xds_service_host,
                    global_backend_service.name)
        url_map = gcp.create_url_map(compute, project,
                                     url_map_name, url_map_path_matcher_name,
                                     xds_service_host, global_backend_service)

    # Target Proxy
    try:
        target_proxy = gcp.get_target_proxy(compute, project,
                                            target_proxy_name)
        logger.info('Loaded target proxy %s', target_proxy.name)
    except google_api_errors.HttpError:
        logger.info('Creating target proxy %s to url map %s',
                    target_proxy_name, url_map.url)
        target_proxy = gcp.create_target_proxy(
            compute, project,
            target_proxy_name, url_map)

    # Global Forwarding Rule
    try:
        forwarding_rule = gcp.get_forwarding_rule(compute, project,
                                                  forwarding_rule_name)
        logger.info('Loaded forwarding rule %s', forwarding_rule.name)
    except google_api_errors.HttpError:
        logger.info('Creating forwarding rule %s 0.0.0.0:%s -> %s in %s',
                    forwarding_rule_name, xds_service_port,
                    target_proxy.url, network)
        forwarding_rule = gcp.create_forwarding_rule(
            compute, project,
            forwarding_rule_name, xds_service_port,
            target_proxy, network)


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # local args shortcuts
    project: str = args.project_id
    zone: str = args.zone
    network: str = args.network

    # todo(sergiitk): move to args
    dotenv.load_dotenv()
    kube_context_name = os.environ['KUBE_CONTEXT_NAME']
    namespace = os.environ['NAMESPACE']
    service_name = os.environ['SERVICE_NAME']
    service_port = os.environ['SERVICE_PORT']
    health_check_name: str = os.environ['HEALTH_CHECK_NAME']
    global_backend_service_name: str = os.environ['GLOBAL_BACKEND_SERVICE_NAME']
    url_map_name: str = os.environ['URL_MAP_NAME']
    url_map_path_matcher_name: str = os.environ['URL_MAP_PATH_MATCHER_NAME']
    target_proxy_name: str = os.environ['TARGET_PROXY_NAME']
    forwarding_rule_name: str = os.environ['FORWARDING_RULE_NAME']
    xds_service_hostname: str = 'sergii-psm-test-xds-host'
    xds_service_port: str = '8000'
    xds_service_host: str = f'{xds_service_hostname}:{xds_service_port}'

    # Connect k8s
    kube_config.load_kube_config(context=kube_context_name)
    k8s_root: CoreApi = kube_client.CoreApi()
    k8s_core_v1: CoreV1Api = kube_client.CoreV1Api()
    if args.verbose:
        k8s.debug_server_mappings(k8s_root)

    # Create compute client
    # todo(sergiitk): see if cache_discovery=False needed
    compute: google_api.Resource = google_api.build(
        'compute', 'v1', cache_discovery=False)

    configure_traffic_director_on_gke(
        k8s_core_v1, compute,
        project, namespace, network,
        service_name, service_port,
        global_backend_service_name, health_check_name,
        url_map_name, url_map_path_matcher_name,
        target_proxy_name, forwarding_rule_name,
        xds_service_host, xds_service_port)

    # todo(sergiitk): finally/context manager
    compute.close()


if __name__ == '__main__':
    main()
