# Copyright 2019 gRPC authors.
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
"""An example of multiprocess concurrency with gRPC."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from concurrent import futures
import datetime
import logging
import math
import multiprocessing
import os
import platform
import errno
import socket
import sys
import time

import grpc
import prime_pb2
import prime_pb2_grpc

_LOGGER = logging.getLogger(__name__)

_ONE_DAY = datetime.timedelta(days=1)
# _PROCESS_COUNT = multiprocessing.cpu_count()
_PROCESS_COUNT = 3
_THREAD_CONCURRENCY = 1
# _THREAD_CONCURRENCY = _PROCESS_COUNT


def is_prime(n):
    for i in range(2, int(math.ceil(math.sqrt(n)))):
        if n % i == 0:
            return False
    else:
        return True


class PrimeChecker(prime_pb2_grpc.PrimeCheckerServicer):
    def check(self, request, context):
        if multiprocessing.current_process().name == 'Process-3':
            _LOGGER.info("Sleepy")
            time.sleep(3)
            _LOGGER.info("Dead")
            os.kill(os.getpid(), 9)
            # sys.exit(1)

        _LOGGER.info(
            "Determining primality of %s",
            request.candidate,
        )
        return prime_pb2.Primality(isPrime=is_prime(request.candidate))


def _wait_forever(server):
    try:
        while True:
            time.sleep(_ONE_DAY.total_seconds())
    except KeyboardInterrupt:
        server.stop(None)


def _run_server(host, port):
    """Start a server in a subprocess."""
    setup_logger()

    _LOGGER.info("Starting new server with PID %d", os.getpid())
    options = (("grpc.so_reuseport", 1),)

    bind_address=f"{host}:{port}"
    s = get_socket(host, port, listen=False)

    server = grpc.server(
        futures.ThreadPoolExecutor(
            max_workers=_THREAD_CONCURRENCY,
        ),
        options=options,
    )
    prime_pb2_grpc.add_PrimeCheckerServicer_to_server(PrimeChecker(), server)
    server.add_insecure_port(bind_address)
    server.start()
    _wait_forever(server)


# @contextlib.contextmanager
# def _reserve_port():
#     """Find and reserve a port for all subprocesses to use."""
#     sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
#     sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
#     if sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 0:
#         raise RuntimeError("Failed to set SO_REUSEPORT.")
#     sock.bind(("", 0))
#     try:
#         yield sock.getsockname()[1]
#     finally:
#         sock.close()

_DEFAULT_SOCK_OPTIONS = (
    (socket.SO_REUSEADDR, socket.SO_REUSEPORT)
)
_UNRECOVERABLE_ERRNOS = (errno.EADDRINUSE, errno.ENOSR)

def get_socket(
    bind_address="localhost",
    port=0,
    listen=True,
    sock_options=_DEFAULT_SOCK_OPTIONS,
):
    """Opens a socket.

    Useful for reserving a port for a system-under-test.

    Args:
      bind_address: The host to which to bind.
      port: The port to which to bind.
      listen: A boolean value indicating whether or not to listen on the socket.
      sock_options: A sequence of socket options to apply to the socket.

    Returns:
      A tuple containing:
        - the address to which the socket is bound
        - the port to which the socket is bound
        - the socket object itself
    """
    _sock_options = sock_options if sock_options else []
    if socket.has_ipv6:
        address_families = (socket.AF_INET6, socket.AF_INET)
    else:
        address_families = (socket.AF_INET,)
    for address_family in address_families:
        try:
            sock = socket.socket(address_family, socket.SOCK_STREAM)
            for sock_option in _sock_options:
                sock.setsockopt(socket.SOL_SOCKET, sock_option, 1)

            for sock_option in _sock_options:
                val = sock.getsockopt(socket.SOL_SOCKET, sock_option)
                _LOGGER.info(f'{sock_option=} {val=}')

            sock.bind((bind_address, port))
            if listen:
                sock.listen(1)
            return bind_address, sock.getsockname()[1], sock
        except OSError as os_error:
            sock.close()
            if os_error.errno in _UNRECOVERABLE_ERRNOS:
                raise
            else:
                continue
    raise RuntimeError(
        "Failed to bind to {} with sock_options {}".format(
            bind_address, sock_options
        )
    )


def main():
    # Check if we're on macOS and warn about SO_REUSEPORT limitations
    if platform.system() == "Darwin":
        _LOGGER.warning(
            "⚠️  WARNING: Running on macOS (Darwin). SO_REUSEPORT behavior "
            "on macOS is different from Linux."
        )
        _LOGGER.warning(
            "   On macOS, SO_REUSEPORT does not provide true "
            "load balancing - all requests from the same"
        )
        _LOGGER.warning(
            "   connection will be handled by the same process, "
            "defeating the purpose of multiprocessing."
        )
        _LOGGER.warning("   This is the issue described in GitHub #40444.")
        _LOGGER.warning(
            "   For true multiprocessing on macOS, "
            "consider using multiple worker processes on different ports."
        )
        sys.stdout.flush()

    host, port, sock = get_socket(listen=False)
    bind_address=f"{host}:{port}"
    _LOGGER.info("Binding to '%s'", bind_address)

    workers = []
    for _ in range(_PROCESS_COUNT):
        # NOTE: It is imperative that the worker subprocesses be forked before
        # any gRPC servers start up. See
        # https://github.com/grpc/grpc/issues/16001 for more details.
        worker = multiprocessing.Process(
            target=_run_server, args=(host, port,),
        )
        # worker.start()
        workers.append(worker)

    for worker in workers:
        worker.start()

    try:
        for worker in workers:
            worker.join(timeout=10)
    except KeyboardInterrupt:
        print("Terminating processes...")
        for worker in workers:
            worker.terminate()


    # with _reserve_port() as port:
    #     bind_address = "localhost:{}".format(port)
    #     sys.stdout.flush()



def setup_logger():
    # handler = logging.StreamHandler(sys.stdout)
    # formatter = logging.Formatter("[PID %(process)d] %(message)s")
    # handler.setFormatter(formatter)
    # _LOGGER.addHandler(handler)
    # _LOGGER.setLevel(logging.INFO)
    logging.basicConfig(
        level=logging.INFO,
        style="{",
        format="[{process} {processName} {thread} {threadName}] {message}",
        datefmt="%m%d %H:%M:%S",
    )

if __name__ == "__main__":
    setup_logger()
    # multiprocessing.set_start_method(method="spawn")
    multiprocessing.set_start_method(method="forkserver")
    main()
