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
import googleapiclient.discovery
from google.cloud import container_v1


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
    compute = googleapiclient.discovery.build('compute', 'v1')

    instances = list_instances(compute, args.project_id, args.zone)

    print('Instances in project %s and zone %s:' % (args.project_id, args.zone))
    for instance in instances:
        print(' - ' + instance['name'])


    print()

    gke = container_v1.ClusterManagerClient()
    print('Clusters in project %s and zone %s:' % (args.project_id, args.zone))
    resp = gke.list_clusters(
        parent=f'projects/{args.project_id}/locations/{args.zone}')

    for cluster in resp.clusters:
        print(' - ' + cluster.name)

  # request = {'project_id': "project_id", 'zone': "us-central1-a", 'parent': "parent"}



if __name__ == '__main__':
    main()


# containers = googleapiclient.discovery.build('container', 'v1')
# containers.list()
