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
from typing import Tuple

import grpc

from src.proto.grpc.testing import test_pb2_grpc
from src.proto.grpc.testing import messages_pb2

logger = logging.getLogger()


class XdsTestClient:
    DEFAULT_STATS_REQUEST_TIMEOUT_SEC = 1200
    CONNECTION_TIMEOUT_SEC = 60

    def __init__(self, host: str, stats_port: Tuple[int, str]):
        self.host = host
        self.stats_service_port = int(stats_port)

    @property
    def stats_service_address(self) -> str:
        return f'{self.host}:{self.stats_service_port}'

    def request_load_balancer_stats(self, num_rpcs, timeout_sec=None):
        if timeout_sec is None:
            timeout_sec = self.DEFAULT_STATS_REQUEST_TIMEOUT_SEC
        request_timeout = timeout_sec + self.CONNECTION_TIMEOUT_SEC

        with grpc.insecure_channel(self.stats_service_address) as channel:
            logger.info('Invoking GetClientStats RPC on %s',
                        self.stats_service_address)

            stub = test_pb2_grpc.LoadBalancerStatsServiceStub(channel)
            stats_request = messages_pb2.LoadBalancerStatsRequest(
                num_rpcs=num_rpcs, timeout_sec=timeout_sec)
            response = stub.GetClientStats(stats_request,
                                           wait_for_ready=True,
                                           timeout=request_timeout)

            logger.info('Invoked GetClientStats RPC to %s: %s',
                        self.stats_service_address, response)
            return response
