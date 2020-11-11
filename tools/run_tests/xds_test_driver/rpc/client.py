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

import grpc

from src.proto.grpc.testing import test_pb2_grpc
from src.proto.grpc.testing import messages_pb2

logger = logging.getLogger()

_CONNECTION_TIMEOUT_SEC = 60
_RPC_TIMEOUT_SEC = 1200


def get_stats(client_addr, client_port, num_rpcs, timeout_sec=_RPC_TIMEOUT_SEC):
    client_host = f'{client_addr}:{client_port}'
    with grpc.insecure_channel(client_host) as channel:
        stub = test_pb2_grpc.LoadBalancerStatsServiceStub(channel)
        request = messages_pb2.LoadBalancerStatsRequest()
        request.num_rpcs = num_rpcs
        request.timeout_sec = timeout_sec
        rpc_timeout = timeout_sec + _CONNECTION_TIMEOUT_SEC

        logger.info('Invoking GetClientStats RPC to %s', client_host)
        response = stub.GetClientStats(
            request, wait_for_ready=True, timeout=rpc_timeout)
        logger.info('Invoked GetClientStats RPC to %s: %s', client_host,
                    response)

        return response
