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

import retrying

logger = logging.getLogger()

_WAIT_FOR_BACKEND_SEC = 1200
_WAIT_FOR_OPERATION_SEC = 1200
_WAIT_FIXES_SEC = 2
_GCP_API_RETRIES = 5


class GcpResource:
    def __init__(self, name, url):
        self.name = name
        self.url = url

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.url!r})'


class ZonalGcpResource(GcpResource):
    def __init__(self, name, url, zone):
        super().__init__(name, url)
        self.zone = zone

    def __repr__(self):
        return f'{self.__class__.__name__}({self.name!r}, {self.url!r}, ' \
               f'{self.zone!r})'


@retrying.retry(retry_on_result=lambda result: result['status'] != 'DONE',
                stop_max_delay=_WAIT_FOR_OPERATION_SEC * 1000,
                wait_fixed=_WAIT_FIXES_SEC * 1000)
def _wait_for_global_operation_with_retry(compute, project, operation):
    return compute.globalOperations().get(
        project=project,
        operation=operation).execute(num_retries=_GCP_API_RETRIES)


def wait_for_global_operation(compute, project, operation):
    result = _wait_for_global_operation_with_retry(compute, project, operation)
    if 'error' in result:
        raise Exception(
            f'Operation {operation} did not complete within {_WAIT_FOR_OPERATION_SEC}')


@retrying.retry(retry_on_result=lambda result: not result,
                stop_max_delay=_WAIT_FOR_BACKEND_SEC * 1000,
                wait_fixed=_WAIT_FIXES_SEC * 1000)
def wait_for_backends_healthy_status(compute, project,
                                     backend_service, backends):
    for backend in backends:
        logger.info("Requesting health: %s", backend.name)
        result = compute.backendServices().getHealth(
            project=project, backendService=backend_service.name,
            body={"group": backend.url}).execute()

        for instance in result['healthStatus']:
            logger.info(
                'Backend %s in zone %s: instance %s:%s - health state: %s',
                backend.name, backend.zone,
                instance['ipAddress'], instance['port'],
                instance['healthState'])

            if instance['healthState'] != 'HEALTHY':
                return False

    return True


def get_health_check(compute, project, health_check_name):
    result = compute.healthChecks().get(project=project,
                                        healthCheck=health_check_name).execute()
    return GcpResource(health_check_name, result['selfLink'])


def create_tcp_health_check(compute, project, health_check_name):
    tcp_health_check_spec = {
        'name': health_check_name,
        'type': 'TCP',
        'tcpHealthCheck': {
            'portSpecification': 'USE_SERVING_PORT',
        }
    }
    result = compute.healthChecks().insert(
        project=project,
        body=tcp_health_check_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(result['name'], result['targetLink'])


def get_backend_service(compute, project, backend_service_name):
    result = compute.backendServices().get(
        project=project,
        backendService=backend_service_name).execute()
    return GcpResource(backend_service_name, result['selfLink'])


def create_backend_service(compute, project,
                           backend_service_name,
                           health_check):
    backend_service_spec = {
        'name': backend_service_name,
        'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
        'healthChecks': [health_check.url],
        'protocol': 'GRPC',
    }
    result = compute.backendServices().insert(
        project=project,
        body=backend_service_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(backend_service_name, result['targetLink'])


def backend_service_add_backend(compute, project,
                                backend_service, negs):
    backends = [{
        'group': neg.url,
        'balancingMode': 'RATE',
        'maxRatePerEndpoint': 5
    } for neg in negs]

    result = compute.backendServices().patch(
        project=project,
        backendService=backend_service.name,
        body={'backends': backends}).execute(num_retries=_GCP_API_RETRIES)

    wait_for_global_operation(
        compute, project, result['name'], timeout_sec=_WAIT_FOR_BACKEND_SEC)


def get_network_endpoint_group(compute, project, zone, neg_name):
    result = compute.networkEndpointGroups().get(
        project=project,
        zone=zone,
        networkEndpointGroup=neg_name).execute()
    return ZonalGcpResource(neg_name, result['selfLink'], zone)


def create_url_map(compute, project,
                   url_map_name, url_map_path_matcher_name,
                   xds_service, backend_service):
    url_map_spec = {
        'name': url_map_name,
        'defaultService': backend_service.url,
        'pathMatchers': [{
            'name': url_map_path_matcher_name,
            'defaultService': backend_service.url,
        }],
        'hostRules': [{
            'hosts': [xds_service],
            'pathMatcher': url_map_path_matcher_name,
        }]
    }
    result = compute.urlMaps().insert(
        project=project,
        body=url_map_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(url_map_name, result['targetLink'])


def create_forwarding_rule(compute, project,
                           forwarding_rule_name, xds_service_port,
                           target_proxy, network):
    forwarding_rule_spec = {
        'name': forwarding_rule_name,
        'loadBalancingScheme': 'INTERNAL_SELF_MANAGED',  # Traffic Director
        'portRange': xds_service_port,
        'IPAddress': '0.0.0.0',
        'network': network,
        'target': target_proxy.url,
    }
    result = compute.globalForwardingRules().insert(
        project=project,
        body=forwarding_rule_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(forwarding_rule_name, result['targetLink'])


def get_url_map(compute, project, url_map_name):
    result = compute.urlMaps().get(project=project,
                                   urlMap=url_map_name).execute()
    return GcpResource(url_map_name, result['selfLink'])


def get_forwarding_rule(compute, project, forwarding_rule_name):
    result = compute.globalForwardingRules().get(
        project=project, forwardingRule=forwarding_rule_name).execute()
    return GcpResource(forwarding_rule_name, result['selfLink'])


def create_target_proxy(compute, project, target_proxy_name, url_map):
    target_proxy_spec = {
        'name': target_proxy_name,
        'url_map': url_map.url,
        'validate_for_proxyless': True,
    }
    result = compute.targetGrpcProxies().insert(
        project=project,
        body=target_proxy_spec).execute(num_retries=_GCP_API_RETRIES)
    wait_for_global_operation(compute, project, result['name'])
    return GcpResource(target_proxy_name, result['targetLink'])


def get_target_proxy(compute, project, target_proxy_name):
    result = compute.targetGrpcProxies().get(
        project=project, targetGrpcProxy=target_proxy_name).execute()
    return GcpResource(target_proxy_name, result['selfLink'])
