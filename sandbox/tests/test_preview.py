import base64
import json
import os
from pathlib import Path
import socket
import stat
import tempfile
import unittest

from deskharbor_sandbox.broker import decode_request
from deskharbor_sandbox.client import encode

class PreviewTests(unittest.TestCase):
    def test_port_and_field_validation(self):
        for port in (22, 0, 65536, True, '3000', None):
            with self.assertRaises(ValueError):
                decode_request(encode({'version': 1, 'action': 'preview', 'project': 'p', 'port': port}))
        self.assertEqual(decode_request(encode({'version': 1, 'action': 'preview', 'project': 'p', 'port': 3000}))['port'], 3000)
        for project in (None, [], {}, 4):
            with self.assertRaises(ValueError):
                decode_request(encode({'version': 1, 'action': 'preview', 'project': project, 'port': 3000}))

    def test_pinned_unix_socket_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'gateway.sock'
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(path))
                listener.listen()
                fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
                try:
                    self.assertTrue(stat.S_ISSOCK(os.fstat(fd).st_mode))
                    with socket.socket(socket.AF_UNIX) as client:
                        client.connect(f'/proc/self/fd/{fd}')
                        peer, _ = listener.accept()
                        with peer:
                            client.sendall(b'preview')
                            self.assertEqual(peer.recv(7), b'preview')
                finally:
                    os.close(fd)
                path.unlink()
                path.symlink_to('/var/run/docker.sock')
                fd = os.open(path, os.O_PATH | os.O_NOFOLLOW)
                try:
                    self.assertFalse(stat.S_ISSOCK(os.fstat(fd).st_mode))
                finally:
                    os.close(fd)
