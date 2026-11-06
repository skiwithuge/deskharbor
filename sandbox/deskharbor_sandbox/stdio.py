"""Byte relay for a socket and SSH standard pipes, without command parsing."""
import os
import selectors


def relay(sock, input_fd=0, output_fd=1):
    with selectors.DefaultSelector() as selector:
        selector.register(input_fd, selectors.EVENT_READ)
        selector.register(sock, selectors.EVENT_READ)
        while events := selector.select(300):
            for key, _ in events:
                if key.fileobj == input_fd:
                    data = os.read(input_fd, 65536)
                    if not data:
                        sock.shutdown(1)
                        selector.unregister(input_fd)
                        continue
                    sock.sendall(data)
                else:
                    data = sock.recv(65536)
                    if not data:
                        return
                    while data:
                        count = os.write(output_fd, data)
                        data = data[count:]
