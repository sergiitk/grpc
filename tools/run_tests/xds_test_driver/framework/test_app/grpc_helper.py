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
from typing import Optional

from google import protobuf
import grpc

logger = logging.getLogger(__name__)

DEFAULT_RPC_TIMEOUT_SEC = 60
DEFAULT_WAIT_READY_TIMEOUT_SEC = 60

# Type aliases
Message = protobuf.message.Message


def call_unary_when_ready(
    *,
    method: grpc.UnaryUnaryMultiCallable,
    request: Message,
    rpc_timeout_sec: Optional[int] = GRPC_DEFAULT_TIMEOUT_SEC
    wait_ready_sec: Optional[int] = GRPC_DEFAULT_TIMEOUT_SEC
) -> Message:
    if rpc_timeout_sec is None:
        rpc_timeout_sec = DEFAULT_RPC_TIMEOUT_SEC
    if connection_timeout_sec is None:
        connection_timeout_sec = DEFAULT_RPC_TIMEOUT_SEC
    timeout_sec =  rpc_timeout_sec + connection_timeout_sec
    return method(request, wait_for_ready=True, timeout=timeout_sec)
