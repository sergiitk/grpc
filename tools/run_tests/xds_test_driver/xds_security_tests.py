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
from pprint import pprint

import googleapiclient.discovery
# from google.cloud import container_v1
from kubernetes import client, config
from kubernetes.client import configuration
from kubernetes.client import ApiException


def parse_args():
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
        '--verbose', action='store_false',
        help='verbose log output')
    return parser.parse_args()


# def create_service():
#
#     compute = googleapiclient.discovery.build('compute', 'v1')
#     result = gcp.compute.instanceGroups().listInstances(
#         project=gcp.project,
#         zone=instance_group.zone,
#         instanceGroup=instance_group.name,
#         body={
#             'instanceState': 'ALL'
#     }).execute(num_retries=_GCP_API_RETRIES)


def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None


def main():
    args = parse_args()
    # print(args)


    # instances = list_instances(compute, args.project_id, args.zone)
    #
    # print('Instances in project %s and zone %s:' % (args.project_id, args.zone))
    # for instance in instances:
    #     print(' - ' + instance['name'])
    #
    # print()
    contexts, active_context = config.list_kube_config_contexts()
    # print(contexts)
    # print(active_context)
    config.load_kube_config(context='gke_grpc-testing_us-central1-a_gke-interop-xds-test1-us-central1')
    # config.load_kube_config(context=active_context['name'])
    core = client.CoreApi()
    v1 = client.CoreV1Api()

    print("Server mappings:")
    for mapping in core.get_api_versions().server_address_by_client_cid_rs:
        print(f"{mapping.client_cidr} -> {mapping.server_address}")

    namespace = 'default'
    service_name = "psm-grpc-service"
    service_port = "8080"
    project = args.project_id
    zone = args.zone

    print(f"Detecting NEG name for service {service_name}")
    service = v1.read_namespaced_service(name=service_name, namespace=namespace)
    neg_info = json.loads(service.metadata.annotations['cloud.google.com/neg-status'])
    neg_name = neg_info['network_endpoint_groups']['8080']

    print(f"Detected NEG = {neg_name}")
    # print(f"NEG = {neg_info.network_endpoint_groups} in zones {neg_info.zones}")

    compute = googleapiclient.discovery.build('compute', 'v1')
    result = compute.networkEndpointGroups().get(project=project, zone=zone, networkEndpointGroup=neg_name).execute()
    print(result)


    # print("Listing pods with their IPs:")
    # ret = v1.list_namespaced_pod(namespace="default")
    # for item in ret.items:
    #     print(
    #         "%s\t%s\t%s" %
    #         (item.status.pod_ip,
    #          item.metadata.namespace,
    #          item.metadata.name))


    # config.load_kube_config()
    # core = client.CoreV1Api()
    #
    # # print("k8s nodes:")
    # core = client.CoreV1Api()
    # for node in core.list_node().items:
    #     print(' - ' + node.metadata.name)
    #
    # print()
    # print("Supported APIs (* is preferred version):")
    # print("%-40s %s" %
    #       ("core", ",".join(client.CoreApi().get_api_versions().versions)))
    # for api in client.ApisApi().get_api_versions().groups:
    #     versions = []
    #     for v in api.versions:
    #         name = ""
    #         if v.version == api.preferred_version.version and len(
    #                 api.versions) > 1:
    #             name += "*"
    #         name += v.version
    #         versions.append(name)
    #     print("%-40s %s" % (api.name, ",".join(versions)))

    # # Enter a context with an instance of the API kubernetes.client
    # with client.ApiClient() as api_client:
    #     # Create an instance of the API class
    #     api_instance = client.AdmissionregistrationApi(api_client)
    #
    #     try:
    #         api_response = api_instance.get_api_group()
    #         pprint(api_response)
    #     except ApiException as e:
    #         print("Exception when calling AdmissionregistrationApi->get_api_group: %s\n" % e)




    # print()
    #
    # gke = container_v1.ClusterManagerClient()
    # print('Clusters in project %s and zone %s:' % (args.project_id, args.zone))
    # resp = gke.list_clusters(
    #     parent='projects/%s/locations/%s' % (args.project_id, args.zone))
    #
    # for cluster in resp.clusters:
    #     print(' - ' + cluster.name)

  # request = {'project_id': "project_id", 'zone': "us-central1-a", 'parent': "parent"}



if __name__ == '__main__':
    main()


# containers = googleapiclient.discovery.build('container', 'v1')
# containers.list()
