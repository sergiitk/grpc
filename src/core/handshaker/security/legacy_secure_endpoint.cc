//
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
//

#include <grpc/event_engine/memory_allocator.h>
#include <grpc/event_engine/memory_request.h>
#include <grpc/slice.h>
#include <grpc/slice_buffer.h>
#include <grpc/support/alloc.h>
#include <grpc/support/atm.h>
#include <grpc/support/port_platform.h>
#include <grpc/support/sync.h>
#include <inttypes.h>

#include <algorithm>
#include <atomic>
#include <memory>
#include <optional>
#include <utility>

#include "absl/base/thread_annotations.h"
#include "absl/log/check.h"
#include "absl/log/log.h"
#include "absl/status/status.h"
#include "absl/strings/string_view.h"
#include "src/core/handshaker/security/secure_endpoint.h"
#include "src/core/lib/debug/trace.h"
#include "src/core/lib/experiments/experiments.h"
#include "src/core/lib/iomgr/closure.h"
#include "src/core/lib/iomgr/endpoint.h"
#include "src/core/lib/iomgr/error.h"
#include "src/core/lib/iomgr/exec_ctx.h"
#include "src/core/lib/iomgr/iomgr_fwd.h"
#include "src/core/lib/resource_quota/api.h"
#include "src/core/lib/resource_quota/memory_quota.h"
#include "src/core/lib/resource_quota/resource_quota.h"
#include "src/core/lib/slice/slice.h"
#include "src/core/lib/slice/slice_string_helpers.h"
#include "src/core/tsi/transport_security_grpc.h"
#include "src/core/tsi/transport_security_interface.h"
#include "src/core/util/debug_location.h"
#include "src/core/util/orphanable.h"
#include "src/core/util/ref_counted_ptr.h"
#include "src/core/util/string.h"
#include "src/core/util/sync.h"

#define STAGING_BUFFER_SIZE 8192

static void on_read(void* user_data, grpc_error_handle error);
static void on_write(void* user_data, grpc_error_handle error);

namespace {
struct secure_endpoint : public grpc_endpoint {
  secure_endpoint(const grpc_endpoint_vtable* vtbl,
                  tsi_frame_protector* protector,
                  tsi_zero_copy_grpc_protector* zero_copy_protector,
                  grpc_core::OrphanablePtr<grpc_endpoint> endpoint,
                  grpc_slice* leftover_slices,
                  const grpc_channel_args* channel_args,
                  size_t leftover_nslices)
      : wrapped_ep(std::move(endpoint)),
        protector(protector),
        zero_copy_protector(zero_copy_protector) {
    this->vtable = vtbl;
    gpr_mu_init(&protector_mu);
    GRPC_CLOSURE_INIT(&on_read, ::on_read, this, grpc_schedule_on_exec_ctx);
    GRPC_CLOSURE_INIT(&on_write, ::on_write, this, grpc_schedule_on_exec_ctx);
    grpc_slice_buffer_init(&source_buffer);
    grpc_slice_buffer_init(&leftover_bytes);
    for (size_t i = 0; i < leftover_nslices; i++) {
      grpc_slice_buffer_add(&leftover_bytes,
                            grpc_core::CSliceRef(leftover_slices[i]));
    }
    grpc_slice_buffer_init(&output_buffer);
    memory_owner = grpc_core::ResourceQuotaFromChannelArgs(channel_args)
                       ->memory_quota()
                       ->CreateMemoryOwner();
    self_reservation = memory_owner.MakeReservation(sizeof(*this));
    if (zero_copy_protector) {
      read_staging_buffer = grpc_empty_slice();
      write_staging_buffer = grpc_empty_slice();
    } else {
      read_staging_buffer =
          memory_owner.MakeSlice(grpc_core::MemoryRequest(STAGING_BUFFER_SIZE));
      write_staging_buffer =
          memory_owner.MakeSlice(grpc_core::MemoryRequest(STAGING_BUFFER_SIZE));
    }
    has_posted_reclaimer.store(false, std::memory_order_relaxed);
    min_progress_size = 1;
    grpc_slice_buffer_init(&protector_staging_buffer);
    gpr_ref_init(&ref, 1);
  }

  ~secure_endpoint() {
    tsi_frame_protector_destroy(protector);
    tsi_zero_copy_grpc_protector_destroy(zero_copy_protector);
    grpc_slice_buffer_destroy(&source_buffer);
    grpc_slice_buffer_destroy(&leftover_bytes);
    grpc_core::CSliceUnref(read_staging_buffer);
    grpc_core::CSliceUnref(write_staging_buffer);
    grpc_slice_buffer_destroy(&output_buffer);
    grpc_slice_buffer_destroy(&protector_staging_buffer);
    gpr_mu_destroy(&protector_mu);
  }

  grpc_core::OrphanablePtr<grpc_endpoint> wrapped_ep;
  struct tsi_frame_protector* protector;
  struct tsi_zero_copy_grpc_protector* zero_copy_protector;
  gpr_mu protector_mu;
  grpc_core::Mutex read_mu;
  grpc_core::Mutex write_mu;
  // saved upper level callbacks and user_data.
  grpc_closure* read_cb = nullptr;
  grpc_closure* write_cb = nullptr;
  grpc_closure on_read;
  grpc_closure on_write;
  grpc_slice_buffer* read_buffer = nullptr;
  grpc_slice_buffer source_buffer;
  // saved handshaker leftover data to unprotect.
  grpc_slice_buffer leftover_bytes;
  // buffers for read and write
  grpc_slice read_staging_buffer ABSL_GUARDED_BY(read_mu);
  grpc_slice write_staging_buffer ABSL_GUARDED_BY(write_mu);
  grpc_slice_buffer output_buffer;
  grpc_core::MemoryOwner memory_owner;
  grpc_core::MemoryAllocator::Reservation self_reservation;
  std::atomic<bool> has_posted_reclaimer;
  int min_progress_size;
  grpc_slice_buffer protector_staging_buffer;
  gpr_refcount ref;
};
}  // namespace

static void destroy(secure_endpoint* ep) { delete ep; }

#ifndef NDEBUG
#define SECURE_ENDPOINT_UNREF(ep, reason) \
  secure_endpoint_unref((ep), (reason), __FILE__, __LINE__)
#define SECURE_ENDPOINT_REF(ep, reason) \
  secure_endpoint_ref((ep), (reason), __FILE__, __LINE__)
static void secure_endpoint_unref(secure_endpoint* ep, const char* reason,
                                  const char* file, int line) {
  if (GRPC_TRACE_FLAG_ENABLED(secure_endpoint)) {
    gpr_atm val = gpr_atm_no_barrier_load(&ep->ref.count);
    VLOG(2).AtLocation(file, line) << "SECENDP unref " << ep << " : " << reason
                                   << " " << val << " -> " << val - 1;
  }
  if (gpr_unref(&ep->ref)) {
    destroy(ep);
  }
}

static void secure_endpoint_ref(secure_endpoint* ep, const char* reason,
                                const char* file, int line) {
  if (GRPC_TRACE_FLAG_ENABLED(secure_endpoint)) {
    gpr_atm val = gpr_atm_no_barrier_load(&ep->ref.count);
    VLOG(2).AtLocation(file, line) << "SECENDP   ref " << ep << " : " << reason
                                   << " " << val << " -> " << val + 1;
  }
  gpr_ref(&ep->ref);
}
#else
#define SECURE_ENDPOINT_UNREF(ep, reason) secure_endpoint_unref((ep))
#define SECURE_ENDPOINT_REF(ep, reason) secure_endpoint_ref((ep))
static void secure_endpoint_unref(secure_endpoint* ep) {
  if (gpr_unref(&ep->ref)) {
    destroy(ep);
  }
}

static void secure_endpoint_ref(secure_endpoint* ep) { gpr_ref(&ep->ref); }
#endif

static void maybe_post_reclaimer(secure_endpoint* ep) {
  if (!ep->has_posted_reclaimer) {
    SECURE_ENDPOINT_REF(ep, "benign_reclaimer");
    ep->has_posted_reclaimer.exchange(true, std::memory_order_relaxed);
    ep->memory_owner.PostReclaimer(
        grpc_core::ReclamationPass::kBenign,
        [ep](std::optional<grpc_core::ReclamationSweep> sweep) {
          if (sweep.has_value()) {
            GRPC_TRACE_LOG(resource_quota, INFO)
                << "secure endpoint: benign reclamation to free memory";
            grpc_slice temp_read_slice;
            grpc_slice temp_write_slice;

            ep->read_mu.Lock();
            temp_read_slice = ep->read_staging_buffer;
            ep->read_staging_buffer = grpc_empty_slice();
            ep->read_mu.Unlock();

            ep->write_mu.Lock();
            temp_write_slice = ep->write_staging_buffer;
            ep->write_staging_buffer = grpc_empty_slice();
            ep->write_mu.Unlock();

            grpc_core::CSliceUnref(temp_read_slice);
            grpc_core::CSliceUnref(temp_write_slice);
            ep->has_posted_reclaimer.exchange(false, std::memory_order_relaxed);
          }
          SECURE_ENDPOINT_UNREF(ep, "benign_reclaimer");
        });
  }
}

static void flush_read_staging_buffer(secure_endpoint* ep, uint8_t** cur,
                                      uint8_t** end)
    ABSL_EXCLUSIVE_LOCKS_REQUIRED(ep->read_mu) {
  grpc_slice_buffer_add_indexed(ep->read_buffer, ep->read_staging_buffer);
  ep->read_staging_buffer =
      ep->memory_owner.MakeSlice(grpc_core::MemoryRequest(STAGING_BUFFER_SIZE));
  *cur = GRPC_SLICE_START_PTR(ep->read_staging_buffer);
  *end = GRPC_SLICE_END_PTR(ep->read_staging_buffer);
}

static void call_read_cb(secure_endpoint* ep, grpc_error_handle error) {
  if (GRPC_TRACE_FLAG_ENABLED(secure_endpoint) && ABSL_VLOG_IS_ON(2)) {
    size_t i;
    for (i = 0; i < ep->read_buffer->count; i++) {
      char* data = grpc_dump_slice(ep->read_buffer->slices[i],
                                   GPR_DUMP_HEX | GPR_DUMP_ASCII);
      VLOG(2) << "READ " << ep << ": " << data;
      gpr_free(data);
    }
  }
  ep->read_buffer = nullptr;
  grpc_core::ExecCtx::Run(DEBUG_LOCATION, ep->read_cb, error);
  SECURE_ENDPOINT_UNREF(ep, "read");
}

static void on_read(void* user_data, grpc_error_handle error) {
  unsigned i;
  uint8_t keep_looping = 0;
  tsi_result result = TSI_OK;
  secure_endpoint* ep = static_cast<secure_endpoint*>(user_data);

  {
    grpc_core::MutexLock l(&ep->read_mu);

    // If we were shut down after this callback was scheduled with OK
    // status but before it was invoked, we need to treat that as an error.
    if (ep->wrapped_ep == nullptr && error.ok()) {
      error = absl::CancelledError("secure endpoint shutdown");
    }

    uint8_t* cur = GRPC_SLICE_START_PTR(ep->read_staging_buffer);
    uint8_t* end = GRPC_SLICE_END_PTR(ep->read_staging_buffer);

    if (!error.ok()) {
      grpc_slice_buffer_reset_and_unref(ep->read_buffer);
    } else if (ep->zero_copy_protector != nullptr) {
      // Use zero-copy grpc protector to unprotect.
      int min_progress_size = 1;
      // Get the size of the last frame which is not yet fully decrypted.
      // This estimated frame size is stored in ep->min_progress_size which is
      // passed to the TCP layer to indicate the minimum number of
      // bytes that need to be read to make meaningful progress. This would
      // avoid reading of small slices from the network.
      // TODO(vigneshbabu): Set min_progress_size in the regular (non-zero-copy)
      // frame protector code path as well.
      result = tsi_zero_copy_grpc_protector_unprotect(
          ep->zero_copy_protector, &ep->source_buffer, ep->read_buffer,
          &min_progress_size);
      min_progress_size = std::max(1, min_progress_size);
      ep->min_progress_size = result != TSI_OK ? 1 : min_progress_size;
    } else {
      // Use frame protector to unprotect.
      // TODO(yangg) check error, maybe bail out early
      for (i = 0; i < ep->source_buffer.count; i++) {
        grpc_slice encrypted = ep->source_buffer.slices[i];
        uint8_t* message_bytes = GRPC_SLICE_START_PTR(encrypted);
        size_t message_size = GRPC_SLICE_LENGTH(encrypted);

        while (message_size > 0 || keep_looping) {
          size_t unprotected_buffer_size_written =
              static_cast<size_t>(end - cur);
          size_t processed_message_size = message_size;
          if (grpc_core::IsTsiFrameProtectorWithoutLocksEnabled()) {
            result = tsi_frame_protector_unprotect(
                ep->protector, message_bytes, &processed_message_size, cur,
                &unprotected_buffer_size_written);
          } else {
            gpr_mu_lock(&ep->protector_mu);
            result = tsi_frame_protector_unprotect(
                ep->protector, message_bytes, &processed_message_size, cur,
                &unprotected_buffer_size_written);
            gpr_mu_unlock(&ep->protector_mu);
          }
          if (result != TSI_OK) {
            LOG(ERROR) << "Decryption error: " << tsi_result_to_string(result);
            break;
          }
          message_bytes += processed_message_size;
          message_size -= processed_message_size;
          cur += unprotected_buffer_size_written;

          if (cur == end) {
            flush_read_staging_buffer(ep, &cur, &end);
            // Force to enter the loop again to extract buffered bytes in
            // protector. The bytes could be buffered because of running out of
            // staging_buffer. If this happens at the end of all slices, doing
            // another unprotect avoids leaving data in the protector.
            keep_looping = 1;
          } else if (unprotected_buffer_size_written > 0) {
            keep_looping = 1;
          } else {
            keep_looping = 0;
          }
        }
        if (result != TSI_OK) break;
      }

      if (cur != GRPC_SLICE_START_PTR(ep->read_staging_buffer)) {
        grpc_slice_buffer_add(
            ep->read_buffer,
            grpc_slice_split_head(
                &ep->read_staging_buffer,
                static_cast<size_t>(
                    cur - GRPC_SLICE_START_PTR(ep->read_staging_buffer))));
      }
    }
  }

  if (!error.ok()) {
    call_read_cb(
        ep, GRPC_ERROR_CREATE_REFERENCING("Secure read failed", &error, 1));
    return;
  }

  // TODO(yangg) experiment with moving this block after read_cb to see if it
  // helps latency
  grpc_slice_buffer_reset_and_unref(&ep->source_buffer);

  if (result != TSI_OK) {
    grpc_slice_buffer_reset_and_unref(ep->read_buffer);
    call_read_cb(
        ep, GRPC_ERROR_CREATE(absl::StrCat("Unwrap failed (",
                                           tsi_result_to_string(result), ")")));
    return;
  }

  call_read_cb(ep, absl::OkStatus());
}

static void endpoint_read(grpc_endpoint* secure_ep, grpc_slice_buffer* slices,
                          grpc_closure* cb, bool urgent,
                          int /*min_progress_size*/) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  ep->read_cb = cb;
  ep->read_buffer = slices;
  grpc_slice_buffer_reset_and_unref(ep->read_buffer);

  SECURE_ENDPOINT_REF(ep, "read");
  if (ep->leftover_bytes.count) {
    grpc_slice_buffer_swap(&ep->leftover_bytes, &ep->source_buffer);
    CHECK_EQ(ep->leftover_bytes.count, 0u);
    on_read(ep, absl::OkStatus());
    return;
  }

  grpc_endpoint_read(ep->wrapped_ep.get(), &ep->source_buffer, &ep->on_read,
                     urgent, /*min_progress_size=*/ep->min_progress_size);
}

static void flush_write_staging_buffer(secure_endpoint* ep, uint8_t** cur,
                                       uint8_t** end)
    ABSL_EXCLUSIVE_LOCKS_REQUIRED(ep->write_mu) {
  grpc_slice_buffer_add_indexed(&ep->output_buffer, ep->write_staging_buffer);
  ep->write_staging_buffer =
      ep->memory_owner.MakeSlice(grpc_core::MemoryRequest(STAGING_BUFFER_SIZE));
  *cur = GRPC_SLICE_START_PTR(ep->write_staging_buffer);
  *end = GRPC_SLICE_END_PTR(ep->write_staging_buffer);
  maybe_post_reclaimer(ep);
}

static void on_write(void* user_data, grpc_error_handle error) {
  secure_endpoint* ep = static_cast<secure_endpoint*>(user_data);
  grpc_closure* cb = ep->write_cb;
  ep->write_cb = nullptr;
  SECURE_ENDPOINT_UNREF(ep, "write");
  grpc_core::EnsureRunInExecCtx([cb, error = std::move(error)]() {
    grpc_core::Closure::Run(DEBUG_LOCATION, cb, error);
  });
}

static void endpoint_write(
    grpc_endpoint* secure_ep, grpc_slice_buffer* slices, grpc_closure* cb,
    grpc_event_engine::experimental::EventEngine::Endpoint::WriteArgs args) {
  GRPC_LATENT_SEE_ALWAYS_ON_SCOPE("secure_endpoint write");
  unsigned i;
  tsi_result result = TSI_OK;
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);

  {
    grpc_core::MutexLock l(&ep->write_mu);
    uint8_t* cur = GRPC_SLICE_START_PTR(ep->write_staging_buffer);
    uint8_t* end = GRPC_SLICE_END_PTR(ep->write_staging_buffer);

    grpc_slice_buffer_reset_and_unref(&ep->output_buffer);

    if (GRPC_TRACE_FLAG_ENABLED(secure_endpoint) && ABSL_VLOG_IS_ON(2)) {
      for (i = 0; i < slices->count; i++) {
        char* data =
            grpc_dump_slice(slices->slices[i], GPR_DUMP_HEX | GPR_DUMP_ASCII);
        VLOG(2) << "WRITE " << ep << ": " << data;
        gpr_free(data);
      }
    }

    if (ep->zero_copy_protector != nullptr) {
      // Use zero-copy grpc protector to protect.
      result = TSI_OK;
      // Break the input slices into chunks of size = max_frame_size and call
      // tsi_zero_copy_grpc_protector_protect on each chunk. This ensures that
      // the protector cannot create frames larger than the specified
      // max_frame_size.
      while (slices->length > static_cast<size_t>(args.max_frame_size()) &&
             result == TSI_OK) {
        grpc_slice_buffer_move_first(slices,
                                     static_cast<size_t>(args.max_frame_size()),
                                     &ep->protector_staging_buffer);
        result = tsi_zero_copy_grpc_protector_protect(
            ep->zero_copy_protector, &ep->protector_staging_buffer,
            &ep->output_buffer);
      }
      if (result == TSI_OK && slices->length > 0) {
        result = tsi_zero_copy_grpc_protector_protect(
            ep->zero_copy_protector, slices, &ep->output_buffer);
      }
      grpc_slice_buffer_reset_and_unref(&ep->protector_staging_buffer);
    } else {
      // Use frame protector to protect.
      for (i = 0; i < slices->count; i++) {
        grpc_slice plain = slices->slices[i];
        uint8_t* message_bytes = GRPC_SLICE_START_PTR(plain);
        size_t message_size = GRPC_SLICE_LENGTH(plain);
        while (message_size > 0) {
          size_t protected_buffer_size_to_send = static_cast<size_t>(end - cur);
          size_t processed_message_size = message_size;
          if (grpc_core::IsTsiFrameProtectorWithoutLocksEnabled()) {
            result = tsi_frame_protector_protect(
                ep->protector, message_bytes, &processed_message_size, cur,
                &protected_buffer_size_to_send);
          } else {
            gpr_mu_lock(&ep->protector_mu);
            result = tsi_frame_protector_protect(
                ep->protector, message_bytes, &processed_message_size, cur,
                &protected_buffer_size_to_send);
            gpr_mu_unlock(&ep->protector_mu);
          }
          if (result != TSI_OK) {
            LOG(ERROR) << "Encryption error: " << tsi_result_to_string(result);
            break;
          }
          message_bytes += processed_message_size;
          message_size -= processed_message_size;
          cur += protected_buffer_size_to_send;

          if (cur == end) {
            flush_write_staging_buffer(ep, &cur, &end);
          }
        }
        if (result != TSI_OK) break;
      }
      if (result == TSI_OK) {
        size_t still_pending_size;
        do {
          size_t protected_buffer_size_to_send = static_cast<size_t>(end - cur);
          if (grpc_core::IsTsiFrameProtectorWithoutLocksEnabled()) {
            result = tsi_frame_protector_protect_flush(
                ep->protector, cur, &protected_buffer_size_to_send,
                &still_pending_size);
          } else {
            gpr_mu_lock(&ep->protector_mu);
            result = tsi_frame_protector_protect_flush(
                ep->protector, cur, &protected_buffer_size_to_send,
                &still_pending_size);
            gpr_mu_unlock(&ep->protector_mu);
          }
          if (result != TSI_OK) break;
          cur += protected_buffer_size_to_send;
          if (cur == end) {
            flush_write_staging_buffer(ep, &cur, &end);
          }
        } while (still_pending_size > 0);
        if (cur != GRPC_SLICE_START_PTR(ep->write_staging_buffer)) {
          grpc_slice_buffer_add(
              &ep->output_buffer,
              grpc_slice_split_head(
                  &ep->write_staging_buffer,
                  static_cast<size_t>(
                      cur - GRPC_SLICE_START_PTR(ep->write_staging_buffer))));
        }
      }
    }
  }

  if (result != TSI_OK) {
    // TODO(yangg) do different things according to the error type?
    grpc_slice_buffer_reset_and_unref(&ep->output_buffer);
    grpc_core::ExecCtx::Run(
        DEBUG_LOCATION, cb,
        GRPC_ERROR_CREATE(
            absl::StrCat("Wrap failed (", tsi_result_to_string(result), ")")));
    return;
  }

  // Need to hold a ref here, because the wrapped endpoint may access
  // output_buffer at any time until the write completes.
  SECURE_ENDPOINT_REF(ep, "write");
  ep->write_cb = cb;
  grpc_endpoint_write(ep->wrapped_ep.get(), &ep->output_buffer, &ep->on_write,
                      std::move(args));
}

static void endpoint_destroy(grpc_endpoint* secure_ep) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  ep->read_mu.Lock();
  ep->wrapped_ep.reset();
  ep->memory_owner.Reset();
  ep->read_mu.Unlock();
  SECURE_ENDPOINT_UNREF(ep, "destroy");
}

static void endpoint_add_to_pollset(grpc_endpoint* secure_ep,
                                    grpc_pollset* pollset) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  grpc_endpoint_add_to_pollset(ep->wrapped_ep.get(), pollset);
}

static void endpoint_add_to_pollset_set(grpc_endpoint* secure_ep,
                                        grpc_pollset_set* pollset_set) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  grpc_endpoint_add_to_pollset_set(ep->wrapped_ep.get(), pollset_set);
}

static void endpoint_delete_from_pollset_set(grpc_endpoint* secure_ep,
                                             grpc_pollset_set* pollset_set) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  grpc_endpoint_delete_from_pollset_set(ep->wrapped_ep.get(), pollset_set);
}

static absl::string_view endpoint_get_peer(grpc_endpoint* secure_ep) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  return grpc_endpoint_get_peer(ep->wrapped_ep.get());
}

static absl::string_view endpoint_get_local_address(grpc_endpoint* secure_ep) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  return grpc_endpoint_get_local_address(ep->wrapped_ep.get());
}

static int endpoint_get_fd(grpc_endpoint* secure_ep) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  return grpc_endpoint_get_fd(ep->wrapped_ep.get());
}

static bool endpoint_can_track_err(grpc_endpoint* secure_ep) {
  secure_endpoint* ep = reinterpret_cast<secure_endpoint*>(secure_ep);
  return grpc_endpoint_can_track_err(ep->wrapped_ep.get());
}

static const grpc_endpoint_vtable vtable = {endpoint_read,
                                            endpoint_write,
                                            endpoint_add_to_pollset,
                                            endpoint_add_to_pollset_set,
                                            endpoint_delete_from_pollset_set,
                                            endpoint_destroy,
                                            endpoint_get_peer,
                                            endpoint_get_local_address,
                                            endpoint_get_fd,
                                            endpoint_can_track_err};

grpc_core::OrphanablePtr<grpc_endpoint> grpc_legacy_secure_endpoint_create(
    struct tsi_frame_protector* protector,
    struct tsi_zero_copy_grpc_protector* zero_copy_protector,
    grpc_core::OrphanablePtr<grpc_endpoint> to_wrap,
    grpc_slice* leftover_slices, const grpc_channel_args* channel_args,
    size_t leftover_nslices) {
  return grpc_core::MakeOrphanable<secure_endpoint>(
      &vtable, protector, zero_copy_protector, std::move(to_wrap),
      leftover_slices, channel_args, leftover_nslices);
}
