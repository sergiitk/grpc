import multiprocessing
import socket
import os
import time

import logging

_LOGGER = logging.getLogger(__name__)


def worker_process(port):
    """Function executed by each child process."""
    setup_logger()
    try:
        # Create a new socket inside the child process
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Set SO_REUSEPORT and SO_REUSEADDR for the new socket
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        s.bind(('0.0.0.0', port))
        s.listen(5)
        _LOGGER.info(f"Process {os.getpid()} listening on port {port}")

        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                _LOGGER.info(f"Process {os.getpid()} received: {data.decode()}")
                # _LOGGER.info(f"Process {os.getpid()} received: {data}")
                conn.sendall(data)

    except Exception as e:
        print(f"Process {os.getpid()} failed: {e}")
    finally:
        if 's' in locals():
            s.close()

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


if __name__ == '__main__':
    # Force the start method to 'spawn' for demonstration (default on macOS)
    setup_logger()
    # multiprocessing.set_start_method('spawn')
    multiprocessing.set_start_method('fork')

    port = 8000
    num_processes = 4
    processes = []

    for _ in range(num_processes):
        p = multiprocessing.Process(target=worker_process, args=(port,))
        processes.append(p)

    for p in processes:
        p.start()

    # Wait for all processes to finish (e.g., with Ctrl+C)
    try:
        for p in processes:
            p.join()
    except KeyboardInterrupt:
        _LOGGER.info("Terminating processes...")
        for p in processes:
            p.terminate()
