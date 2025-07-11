//
// Copyright 2015 gRPC authors.
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

#include "src/core/client_channel/retry_filter.h"

#include <grpc/event_engine/event_engine.h>
#include <grpc/support/port_platform.h>

#include <optional>
#include <string>

#include "absl/status/statusor.h"
#include "absl/strings/strip.h"
#include "src/core/client_channel/client_channel_filter.h"
#include "src/core/client_channel/retry_filter_legacy_call_data.h"
#include "src/core/client_channel/retry_service_config.h"
#include "src/core/client_channel/retry_throttle.h"
#include "src/core/lib/channel/channel_args.h"
#include "src/core/lib/channel/channel_stack.h"
#include "src/core/lib/debug/trace.h"
#include "src/core/service_config/service_config.h"
#include "src/core/service_config/service_config_call_data.h"
#include "src/core/util/ref_counted_ptr.h"
#include "src/core/util/uri.h"

//
// Retry filter
//

// This filter is intended to be used in the DynamicFilter stack in the
// client channel, which is situated between the name resolver and the
// LB policy.  Normally, the last filter in the DynamicFilter stack is
// the DynamicTerminationFilter (see client_channel.cc), which creates a
// LoadBalancedCall and delegates to it.  However, when retries are
// enabled, this filter is used instead of the DynamicTerminationFilter.
//
// In order to support retries, we act as a proxy for stream op batches.
// When we get a batch from the surface, we add it to our list of pending
// batches, and we then use those batches to construct separate "child"
// batches to be started on an LB call.  When the child batches return, we
// then decide which pending batches have been completed and schedule their
// callbacks accordingly.  If a call attempt fails and we want to retry it,
// we create a new LB call and start again, constructing new "child" batches
// for the new LB call.
//
// Note that retries are committed when receiving data from the server
// (except for Trailers-Only responses).  However, there may be many
// send ops started before receiving any data, so we may have already
// completed some number of send ops (and returned the completions up to
// the surface) by the time we realize that we need to retry.  To deal
// with this, we cache data for send ops, so that we can replay them on a
// different LB call even after we have completed the original batches.
//
// The code is structured as follows:
// - In CallData (in the parent channel), we maintain a list of pending
//   ops and cached data for send ops.
// - There is a CallData::CallAttempt object for each retry attempt.
//   This object contains the LB call for that attempt and state to indicate
//   which ops from the CallData object have already been sent down to that
//   LB call.
// - There is a CallData::CallAttempt::BatchData object for each "child"
//   batch sent on the LB call.
//
// When constructing the "child" batches, we compare the state in the
// CallAttempt object against the state in the CallData object to see
// which batches need to be sent on the LB call for a given attempt.

// TODO(roth): In subsequent PRs:
// - implement hedging

using grpc_core::internal::RetryGlobalConfig;
using grpc_core::internal::RetryMethodConfig;
using grpc_core::internal::RetryServiceConfigParser;
using grpc_event_engine::experimental::EventEngine;

namespace grpc_core {

//
// RetryFilter
//

void RetryFilter::UpdateBlackboard(const ServiceConfig& service_config,
                                   const Blackboard* old_blackboard,
                                   Blackboard* new_blackboard) {
  // Get retry throttling parameters from service config.
  const auto* config = static_cast<const RetryGlobalConfig*>(
      service_config.GetGlobalParsedConfig(
          RetryServiceConfigParser::ParserIndex()));
  if (config == nullptr) return;
  // Get throttler.
  RefCountedPtr<internal::RetryThrottler> throttler;
  if (old_blackboard != nullptr) {
    throttler = old_blackboard->Get<internal::RetryThrottler>("");
  }
  throttler = internal::RetryThrottler::Create(config->max_milli_tokens(),
                                               config->milli_token_ratio(),
                                               std::move(throttler));
  new_blackboard->Set("", std::move(throttler));
}

RetryFilter::RetryFilter(const grpc_channel_element_args& args)
    : client_channel_(args.channel_args.GetObject<ClientChannelFilter>()),
      event_engine_(args.channel_args.GetObject<EventEngine>()),
      per_rpc_retry_buffer_size_(
          GetMaxPerRpcRetryBufferSize(args.channel_args)),
      retry_throttler_(args.blackboard->Get<internal::RetryThrottler>("")),
      service_config_parser_index_(
          internal::RetryServiceConfigParser::ParserIndex()) {}

const RetryMethodConfig* RetryFilter::GetRetryPolicy(Arena* arena) {
  auto* svc_cfg_call_data = arena->GetContext<ServiceConfigCallData>();
  if (svc_cfg_call_data == nullptr) return nullptr;
  return static_cast<const RetryMethodConfig*>(
      svc_cfg_call_data->GetMethodParsedConfig(service_config_parser_index_));
}

const grpc_channel_filter RetryFilter::kVtable = {
    RetryFilter::LegacyCallData::StartTransportStreamOpBatch,
    RetryFilter::StartTransportOp,
    sizeof(RetryFilter::LegacyCallData),
    RetryFilter::LegacyCallData::Init,
    RetryFilter::LegacyCallData::SetPollent,
    RetryFilter::LegacyCallData::Destroy,
    sizeof(RetryFilter),
    RetryFilter::Init,
    grpc_channel_stack_no_post_init,
    RetryFilter::Destroy,
    RetryFilter::GetChannelInfo,
    GRPC_UNIQUE_TYPE_NAME_HERE("retry_filter"),
};

}  // namespace grpc_core
