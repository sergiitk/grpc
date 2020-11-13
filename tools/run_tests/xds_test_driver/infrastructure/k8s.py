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

import json
import logging
import pathlib
import contextlib
from typing import Tuple, List

import yaml
from kubernetes import client
from kubernetes import utils

import xds_test_app.client

logger = logging.getLogger()


class ClientRunError(Exception):
    """Error running Test Client"""


def get_service_neg(
    k8s_core_v1: client.CoreV1Api, namespace: str,
    service_name: str, service_port: int,
) -> Tuple[str, List[str]]:
    logger.info('Detecting NEG name for service=%s', service_name)
    service: client.V1Service = k8s_core_v1.read_namespaced_service(
        service_name, namespace)

    neg_info: dict = json.loads(
        service.metadata.annotations['cloud.google.com/neg-stat us'])
    neg_name: str = neg_info['network_endpoint_groups'][str(service_port)]
    neg_zones: List[str] = neg_info['zones']
    return neg_name, neg_zones


def debug_server_mappings(k8s_root: client.CoreApi):
    logger.debug("Server mappings:")
    for mapping in k8s_root.get_api_versions().server_address_by_client_cid_rs:
        logger.debug('%s -> %s', mapping.client_cidr, mapping.server_address)


def create_test_client_deployment(
    k8s_client, namespace,
    deployment_name, template='client.deployment.yaml'
) -> client.V1Deployment:
    # Open template
    yaml_file = pathlib.Path('./templates').joinpath(template).absolute()
    logger.info("Creating client from: %s", yaml_file)

    # Parse yaml
    with open(yaml_file) as f, contextlib.closing(yaml.safe_load_all(f)) as yml:
        manifest = next(yml)
        # Error out on multi-document yaml
        if next(yml, False):
            raise ClientRunError(
                'Exactly one document expected in client manifest {yaml_file}')

    # Apply the manifest
    results = utils.create_from_dict(k8s_client, manifest, namespace=namespace)

    # Correctness check
    if len(results) != 1 or not isinstance(results[0], client.V1Deployment):
        raise ClientRunError('Expected exactly one Deployment created from '
                             f'manifest {yaml_file}')
    deployment: client.V1Deployment = results[0]
    if deployment.metadata.name != deployment_name:
        raise ClientRunError('Client Deployment created with unexpected name: '
                             f'{deployment.metadata.name}')
    logger.info('Deployment %s created at %s',
                deployment.metadata.self_link,
                deployment.metadata.creation_timestamp)

    return deployment


def delete_test_client_deployment(k8s_client, namespace, deployment_name):
    api_apps = client.AppsV1Api(k8s_client)
    api_apps.delete_namespaced_deployment(
        name=deployment_name, namespace=namespace,
        body=client.V1DeleteOptions(
            propagation_policy='Foreground',
            grace_period_seconds=5))
    logger.info('Deployment %s deleted', deployment_name)


def label_dict_to_selector(labels: dict) -> str:
    return ','.join(f'{k}=={v}' for k, v in labels.items())


def list_pods_with_labels(k8s_client,
                          namespace,
                          labels: dict) -> List[client.V1Pod]:
    api_core = client.CoreV1Api(k8s_client)
    pod_list: client.V1PodList = api_core.list_namespaced_pod(
        namespace, label_selector=label_dict_to_selector(labels))
    return pod_list.items


def get_deployment_pods(k8s_client,
                        namespace,
                        deployment: client.V1Deployment) -> List[client.V1Pod]:
    # V1LabelSelector.match_expressions not supported at the moment
    return list_pods_with_labels(
        k8s_client, namespace, deployment.spec.selector.match_labels)


def wait_for_pod_ready(k8s_client, namespace, pod):
    return 1


def get_deployment_by_name(k8s_client, namespace,
                           deployment_name) -> client.V1Deployment:
    api_apps = client.AppsV1Api(k8s_client)
    deployment: client.V1Deployment = api_apps.read_namespaced_deployment(
        deployment_name, namespace)

    logger.info('Loaded Deployment %s', deployment.metadata.self_link)
    return deployment


@contextlib.contextmanager
def xds_test_client(k8s_client, namespace, deployment_name='psm-grpc-client',
                    stats_port=8079, host_override=None):
    deployment: client.V1Deployment

    # Reuse
    deployment = get_deployment_by_name(k8s_client, namespace, deployment_name)
    if not deployment:
        deployment = create_test_client_deployment(k8s_client, namespace,
                                                   deployment_name)

    pods = get_deployment_pods(k8s_client, namespace, deployment)

    # We need only one client at the moment
    pod: client.V1Pod = pods[0]
    wait_for_pod_ready(k8s_client, namespace, pod)

    host: str = pod.status.pod_ip
    if host_override is not None:
        logger.info('Overriding client host %s with %s', host, host_override)
        host = host_override

    yield xds_test_app.client.XdsTestClient(host=host, stats_port=stats_port)

    # delete_test_client_deployment(k8s_client, namespace, deployment_name)


def _debug(k8s_obj):
    print(yaml.dump(k8s_obj.to_dict()))
