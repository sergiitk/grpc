//
// Copyright 2025 gRPC authors.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//

#ifndef GRPC_SRC_CORE_XDS_GRPC_XDS_SERVER_GRPC_INTERFACE_H
#define GRPC_SRC_CORE_XDS_GRPC_XDS_SERVER_GRPC_INTERFACE_H

#include "src/core/credentials/call/call_creds_registry.h"
#include "src/core/credentials/transport/channel_creds_registry.h"
#include "src/core/util/ref_counted_ptr.h"
#include "src/core/xds/xds_client/xds_bootstrap.h"

namespace grpc_core {

class GrpcXdsServerInterface : public XdsBootstrap::XdsServerTarget {
 public:
  virtual RefCountedPtr<ChannelCredsConfig> channel_creds_config() const = 0;

  virtual const std::vector<RefCountedPtr<CallCredsConfig>>&
  call_creds_configs() const = 0;
};

}  // namespace grpc_core

#endif  // GRPC_SRC_CORE_XDS_GRPC_XDS_SERVER_GRPC_INTERFACE_H
