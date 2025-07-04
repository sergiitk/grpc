//
//
// Copyright 2018 gRPC authors.
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
//

#ifndef GRPC_SRC_CORE_TELEMETRY_CONTEXT_LIST_ENTRY_H
#define GRPC_SRC_CORE_TELEMETRY_CONTEXT_LIST_ENTRY_H

#include <grpc/support/port_platform.h>
#include <stddef.h>
#include <stdint.h>

#include <vector>

namespace grpc_core {

class Arena;

using CopyContextFn = void* (*)(Arena*);
using DeleteContextFn = void (*)(void*);

void GrpcHttp2SetCopyContextFn(CopyContextFn fn);
void GrpcHttp2SetDeleteContextFn(DeleteContextFn fn);

CopyContextFn GrpcHttp2GetCopyContextFn();
DeleteContextFn GrpcHttp2GetDeleteContextFn();

/// An RPC trace context and associated information. Each RPC/stream is
/// associated with a unique \a context. A new ContextList entry is created when
/// a chunk of data stored in an outgoing buffer is going to be
// sent over the wire. A data chunk being written over the wire is multiplexed
// with bytes from multiple RPCs. If one such RPC is traced, we store the
// following information about the traced RPC:
class ContextListEntry {
 public:
  ContextListEntry(void* context, int64_t outbuf_offset,
                   int64_t num_traced_bytes, size_t byte_offset,
                   size_t stream_index)
      : trace_context_(context),
        outbuf_offset_(outbuf_offset),
        num_traced_bytes_in_chunk_(num_traced_bytes),
        byte_offset_in_stream_(byte_offset),
        stream_index_(stream_index) {}

  ContextListEntry() = delete;
  ContextListEntry(const ContextListEntry&) = delete;
  ContextListEntry& operator=(const ContextListEntry&) = delete;

  ContextListEntry(ContextListEntry&& other) noexcept
      : trace_context_(other.trace_context_),
        outbuf_offset_(other.outbuf_offset_),
        num_traced_bytes_in_chunk_(other.num_traced_bytes_in_chunk_),
        byte_offset_in_stream_(other.byte_offset_in_stream_),
        stream_index_(other.stream_index_) {
    other.trace_context_ = nullptr;
  }
  ContextListEntry& operator=(ContextListEntry&& other) noexcept {
    if (this != &other) {
      trace_context_ = other.trace_context_;
      other.trace_context_ = nullptr;
      outbuf_offset_ = other.outbuf_offset_;
      num_traced_bytes_in_chunk_ = other.num_traced_bytes_in_chunk_;
      byte_offset_in_stream_ = other.byte_offset_in_stream_;
      stream_index_ = other.stream_index_;
    }
    return *this;
  }

  ~ContextListEntry() {
    if (trace_context_ != nullptr) {
      GrpcHttp2GetDeleteContextFn()(trace_context_);
    }
  }

  void* TraceContext() { return trace_context_; }
  int64_t OutbufOffset() { return outbuf_offset_; }
  int64_t NumTracedBytesInChunk() { return num_traced_bytes_in_chunk_; }
  size_t ByteOffsetInStream() { return byte_offset_in_stream_; }
  size_t StreamIndex() { return stream_index_; }

 private:
  void* trace_context_;
  // Offset of the head of the current chunk in the output buffer.
  int64_t outbuf_offset_;
  // Number of bytes traced in the current chunk.
  int64_t num_traced_bytes_in_chunk_;
  // Offset of the head of the current chunk in the RPC stream.
  size_t byte_offset_in_stream_;
  // Index of the current chunk in the RPC stream.
  // Set to zero for the first chunk of the RPC stream.
  size_t stream_index_;
};

/// A list of RPC Contexts
typedef std::vector<ContextListEntry> ContextList;

}  // namespace grpc_core

#endif  // GRPC_SRC_CORE_TELEMETRY_CONTEXT_LIST_ENTRY_H
