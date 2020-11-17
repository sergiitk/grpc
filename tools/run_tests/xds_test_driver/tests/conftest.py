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

# from typing import Generator

import kubernetes.client
import pytest

# import xds_test_app.client
from infrastructure import k8s


def pytest_addoption(parser):
    group_driver = parser.getgroup('GCP settings')
    group_driver.addoption('--project_id', help='Project ID', required=True)
    group_driver.addoption(
        '--network', default='default-vpc',
        help='Network ID')

    group_driver = parser.getgroup('xDS test client settings')
    group_driver.addoption(
        '--client_host_override', type=str,
        help='Do not detect test client host automatically. Use this options '
             'for debugging locally (with port forwarding)')
    group_driver.addoption(
        '--client_stats_port', default=8079, type=int,
        help='The port of LoadBalancerStatsService on the client')


@pytest.fixture(scope="session")
def app_config(request):
    args = request.config
    return {
        "client_stats_port": args.getoption('client_stats_port'),
        "client_host_override": args.getoption('client_host_override'),
    }


@pytest.fixture(scope="session")
def k8s_api() -> str:
    # todo(sergiitk): context=kube_context_name
    kubernetes.config.load_kube_config()
    with kubernetes.client.ApiClient() as _k8s_client:
        yield _k8s_client


@pytest.fixture(scope="session")
def run_id() -> str:
    # todo(sergiitk): generate automatically
    return 'run-1'


@pytest.fixture(scope="session")
def xds_client_config(request, run_id) -> str:
    opts = request.config
    return {
        'namespace': 'sergii-psm-test',
        # 'namespace': 'psm-grpc-client',
        'stats_port': opts.getoption('client_stats_port'),
        'host_override': opts.getoption('client_host_override'),
    }


@pytest.fixture
def xds_client(k8s_api, xds_client_config):
    cfg = xds_client_config
    with k8s.xds_test_client(k8s_api, cfg['namespace'],
                             stats_port=cfg['stats_port'],
                             host_override=cfg['host_override']) as _xds_client:
        yield _xds_client
