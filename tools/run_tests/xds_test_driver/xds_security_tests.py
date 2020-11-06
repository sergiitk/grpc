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
import time
from typing import List, Tuple

from googleapiclient import discovery as google_api
from googleapiclient import errors as google_api_errors
from kubernetes import client as kube_client
from kubernetes import config as kube_config
from kubernetes.client import CoreV1Api, CoreApi
from kubernetes.client.models import V1Service

# todo(sergiitk): fix imports
_WAIT_FOR_OPERATION_SEC = 1200
_GCP_API_RETRIES = 5

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


def wait_for_global_operation(compute, project, operation,
                              timeout_sec=_WAIT_FOR_OPERATION_SEC):
    start_time = time.time()
    while time.time() - start_time <= timeout_sec:
        result = compute.globalOperations().get(
            project=project,
            operation=operation).execute(num_retries=_GCP_API_RETRIES)
        if result['status'] == 'DONE':
            if 'error' in result:
                raise Exception(result['error'])
            return
        time.sleep(2)
    raise Exception('Operation %s did not complete within %d' %
                    (operation, timeout_sec))


def k8s_get_service_neg(
    k8s_core_v1: CoreV1Api, service_name: str, namespace: str,
    service_port: int,
) -> Tuple[str, List[str]]:
    logger.debug('Detecting NEG name for service=%s', service_name)
    service: V1Service = k8s_core_v1.read_namespaced_service(
        service_name, namespace, async_req=False)

    neg_info: dict = json.loads(
        service.metadata.annotations['cloud.google.com/neg-status'])
    neg_name: str = neg_info['network_endpoint_groups'][str(service_port)]
    neg_zones: List[str] = neg_info['zones']
    return neg_name, neg_zones


def k8s_print_server_mappings(k8s_root):
    logger.debug("Server mappings:")
    for mapping in k8s_root.get_api_versions().server_address_by_client_cid_rs:
        logger.debug('%s -> %s', mapping.client_cidr, mapping.server_address)


class GcpResource:
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.url!r})'


class GcpState:
    def __init__(self, compute, project):
        self.compute = compute
        # self.alpha_compute = alpha_compute
        self.project = project
        self.health_check = None
        self.health_check_firewall_rule = None
        self.backend_services = []
        self.url_map = None
        self.target_proxy = None
        self.global_forwarding_rule = None
        self.service_port = None


def gcp_get_health_check(compute, project, health_check_name):
    result = compute.healthChecks().get(project=project,
                                        healthCheck=health_check_name).execute()
    return GcpResource(health_check_name, result['selfLink'])


def gcp_create_tcp_health_check(compute, project, health_check_name):
    tcp_health_check_spec = {
        'name': health_check_name,
        'type': 'TCP',
        'tcpHealthCheck': {
            'portSpecification': 'USE_SERVING_PORT',
        }
    }
    result = compute.healthChecks().insert(project=project,
                                           body=tcp_health_check_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(result['name'], result['targetLink'])


def gcp_get_backend_service(compute, project, backend_service_name):
    result = compute.backendServices().get(
        project=project,
        backendService=backend_service_name).execute()
    return GcpResource(backend_service_name, result['selfLink'])


def gcp_create_backend_service(compute, project, backend_service_name, health_check):
    backend_service_spec = {
        'name': backend_service_name,
        'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
        'healthChecks': [health_check.url],
        'protocol': 'HTTP2',
    }
    result = compute.backendServices().insert(
        project=project,
        body=backend_service_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(result['name'], result['targetLink'])


def main():
    args = parse_args()
    if not args.verbose:
        logger.setLevel(logging.INFO)

    # local args shortcuts
    project: str = args.project_id
    zone: str = args.zone

    # todo(sergiitk): move to args
    kube_context_name = 'gke_grpc-testing_us-central1-a_gke-interop-xds-test1-us-central1'
    namespace = 'default'
    service_name = 'psm-grpc-service'
    service_port = 8080
    # todo(sergiitk): remove sergii-psm-test-health-check2
    health_check_name: str = "sergii-psm-test-health-check"
    backend_service_name: str = "sergii-psm-test-backend-service"

    # Connect k8s
    kube_config.load_kube_config(context=kube_context_name)
    k8s_root: CoreApi = kube_client.CoreApi()
    k8s_core_v1: CoreV1Api = kube_client.CoreV1Api()

    if args.verbose:
        k8s_print_server_mappings(k8s_root)

    # Detect NEG name
    neg_name, neg_zones = k8s_get_service_neg(k8s_core_v1, service_name,
                                              namespace,
                                              service_port)
    logger.info("Detected NEG=%s in zones=%s", neg_name, neg_zones)

    # todo(sergiitk): see if cache_discovery=False needed
    compute: google_api.Resource = google_api.build('compute', 'v1',
                                                    cache_discovery=False)

    # Health check
    try:
        health_check = gcp_get_health_check(compute, project, health_check_name)
        logger.info('Loaded TCP HealthCheck %s', health_check.name)
    except google_api_errors.HttpError as e:
        logger.info('Creating TCP HealthCheck %s', health_check_name)
        health_check = gcp_create_tcp_health_check(compute, project,
                                                   health_check_name)

    # Backend Service
    backend_services = []
    try:
        backend_service = gcp_get_backend_service(compute, project,
                                                  backend_service_name)
        logger.info('Loaded Backend Service %s', backend_service.name)
    except google_api_errors.HttpError as e:
        logger.info('Creating Backend Service %s', backend_service_name)
        backend_service = gcp_create_backend_service(
            compute, project, backend_service_name, health_check)
    backend_services.append(backend_service)


    # todo(sergiitk): finally/context manager
    compute.close()


if __name__ == '__main__':
    main()
