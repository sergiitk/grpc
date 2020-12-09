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
import logging
import re
from typing import Optional, ClassVar

from google.protobuf import json_format
import google.protobuf.message
import grpc

logger = logging.getLogger(__name__)

# Type aliases
Message = google.protobuf.message.Message


class GrpcClientHelper:
    channel: grpc.Channel
    DEFAULT_CONNECTION_TIMEOUT_SEC = 60
    DEFAULT_WAIT_FOR_READY_SEC = 60

    def __init__(self, channel: grpc.Channel, stub_class: ClassVar):
        self.channel = channel
        self.stub = stub_class(channel)

    def call_unary_when_channel_ready(
        self, *,
        rpc: str,
        request: Message,
        wait_for_ready_sec: Optional[int] = DEFAULT_WAIT_FOR_READY_SEC,
        connection_timeout_sec: Optional[int] = DEFAULT_CONNECTION_TIMEOUT_SEC
    ) -> Message:
        if wait_for_ready_sec is None:
            wait_for_ready_sec = self.DEFAULT_WAIT_FOR_READY_SEC
        if connection_timeout_sec is None:
            connection_timeout_sec = self.DEFAULT_CONNECTION_TIMEOUT_SEC

        timeout_sec = wait_for_ready_sec + connection_timeout_sec
        rpc_callable: grpc.UnaryUnaryMultiCallable = getattr(self.stub, rpc)

        _kwargs = dict(wait_for_ready=True, timeout=timeout_sec)
        logger.debug('RPC %s.%s(request=%s(%r), %s)',
                     re.sub('Stub$', '', self.stub.__class__.__name__),
                     rpc,
                     request.__class__.__name__,
                     json_format.MessageToDict(request),
                     ', '.join({f'{k}={v}' for k, v in _kwargs.items()}))
        return rpc_callable(request, **_kwargs)
