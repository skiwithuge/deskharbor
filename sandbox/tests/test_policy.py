import base64
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from deskharbor_sandbox.broker import decode_request, docker_command, checked_project
from deskharbor_sandbox.client import encode, connection
from deskharbor_sandbox.projectfs import ProjectFS
from deskharbor_sandbox.proxy import public_address, connect_public


class FilesystemTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        (self.root / '.env').write_text('synthetic-secret')
        (self.root / 'normal').write_text('hello')
        (self.root / 'config').mkdir()
        (self.root / 'config' / 'auth.json').write_text('custom-secret')
        self.fs = ProjectFS(self.root, ['config/auth.json'])

    def tearDown(self):
        for handle in list(self.fs.handles):
            self.fs.release('', handle)
        os.close(self.fs.root_fd)
        self.temp.cleanup()

    def test_live_write_and_atomic_rename(self):
        handle = self.fs.create('/temporary', 0o644)
        self.fs.write('/temporary', b'new', 0, handle)
        self.fs.release('/temporary', handle)
        self.fs.rename('/temporary', '/normal')
        self.assertEqual((self.root / 'normal').read_text(), 'new')

    def test_hidden_files_and_nested_new_files(self):
        for path in ('/.env', '/.env.example', '/config/auth.json', '/nested/.env.new',
                     '/secrets/key', '/.ssh/config', '/private.pem'):
            with self.subTest(path=path), self.assertRaises(OSError):
                self.fs.create(path, 0o600)
        (self.root / 'config' / '.env.new').write_text('late-secret')
        self.assertNotIn('.env.new', self.fs.readdir('/config', None))
        with self.assertRaises(OSError):
            self.fs.open('/config/.env.new', os.O_RDONLY)

    def test_traversal_and_symlink_escape(self):
        (self.root / 'escape').symlink_to('/etc/passwd')
        (self.root / 'secret-link').symlink_to('.env')
        (self.root / 'safe-link').symlink_to('normal')
        self.assertEqual(self.fs.readlink('/safe-link'), 'normal')
        for path in ('/escape', '/secret-link'):
            with self.subTest(path=path), self.assertRaises(OSError):
                self.fs.readlink(path)
        for path in ('/../outside', '/config/../../outside'):
            with self.assertRaises(OSError):
                self.fs.open(path, os.O_RDONLY)
        (self.root / 'dir-link').symlink_to('/tmp', target_is_directory=True)
        with self.assertRaises(OSError):
            self.fs.create('/dir-link/escape', 0o644)

    def test_hardlink_alias_never_truncates_secret(self):
        os.link(self.root / '.env', self.root / 'alias')
        with self.assertRaises(OSError):
            self.fs.open('/alias', os.O_WRONLY | os.O_TRUNC)
        self.assertEqual((self.root / '.env').read_text(), 'synthetic-secret')

    def test_held_descriptor_rechecked_after_host_rename(self):
        handle = self.fs.open('/normal', os.O_RDONLY)
        (self.root / 'normal').rename(self.root / '.env.moved')
        with self.assertRaises(OSError):
            self.fs.read('/normal', 5, 0, handle)

    def test_host_directory_move_outside_root(self):
        (self.root / 'nested').mkdir()
        fd, _ = self.fs.parent('/nested/new')
        (self.root / 'nested').rename(Path(self.temp.name) / 'outside')
        try:
            with self.assertRaises(OSError):
                self.fs.check_location(fd)
        finally:
            os.close(fd)

    def test_designated_secret_cannot_be_unmasked_by_parent_rename(self):
        with self.assertRaises(OSError):
            self.fs.rename('/config', '/moved')

    def test_host_socket_and_fifo_hidden(self):
        os.mkfifo(self.root / 'pipe')
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.bind(str(self.root / 'socket'))
            self.assertNotIn('socket', self.fs.readdir('/', None))
            self.assertNotIn('pipe', self.fs.readdir('/', None))
            with self.assertRaises(OSError):
                self.fs.open('/socket', os.O_RDONLY)
        finally:
            sock.close()


class NetworkTests(unittest.TestCase):
    def test_private_special_and_mapped_addresses(self):
        for address in ('127.0.0.1', '192.0.2.10', '10.0.0.1', '172.17.0.1',
                        '169.254.169.254', '100.64.0.1', '224.0.0.1', '::1',
                        'fc00::1', 'fe80::1', '::ffff:192.0.2.10',
                        '64:ff9b::c0a8:11b', '2002:c0a8:11b::1'):
            with self.subTest(address=address):
                self.assertFalse(public_address(address))
        self.assertTrue(public_address('1.1.1.1'))
        self.assertFalse(public_address('1.1.1.1', {'1.1.1.1'}))

    def test_dns_private_result_never_opens_connection(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))]
        with patch('socket.getaddrinfo', return_value=answers), patch('socket.socket') as create:
            with self.assertRaises(PermissionError):
                connect_public('public-looking.example', 443, set())
            create.assert_not_called()

    def test_mixed_dns_results_fail_closed(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 443))
                   for ip in ('1.1.1.1', '10.0.0.1')]
        with patch('socket.getaddrinfo', return_value=answers), patch('socket.socket') as create:
            with self.assertRaises(PermissionError):
                connect_public('mixed.example', 443, set())
            create.assert_not_called()

    def test_dns_pinned_to_validated_numeric_address(self):
        answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('1.1.1.1', 443))]
        with patch('socket.getaddrinfo', return_value=answers) as resolve, patch('socket.socket') as create:
            connect_public('changes.example', 443, set())
            resolve.assert_called_once()
            create.return_value.connect.assert_called_once_with(('1.1.1.1', 443))


class BrokerTests(unittest.TestCase):
    def request(self, **extra):
        request = {'version': 1, 'action': 'run', 'project': 'demo',
                   'agent': 'codex', 'args': [], 'gpu': False}
        request.update(extra)
        return request

    def test_protocol_and_workload_args_do_not_become_host_commands(self):
        request = self.request(args=['--config', 'x=$(touch /host-file)'])
        self.assertEqual(decode_request(encode(request)), request)
        config = {'uid': 1000, 'gid': 1000, 'image': 'sha256:' + 'a' * 64}
        command = docker_command(config, '/unused', '/home', '/view', '/proxy', 'test', request)
        self.assertGreater(command.index('x=$(touch /host-file)'), command.index(config['image']))
        self.assertIn('no-new-privileges', command)
        self.assertIn('--read-only', command)
        self.assertIn('none', command)
        self.assertNotIn('/var/run/docker.sock', ' '.join(command))

    def test_unknown_fields_and_arbitrary_programs_rejected(self):
        for extra in ({'host_path': '/etc'}, {'agent': '/bin/sh'}, {'gpu': 'true'},
                      {'project': '../etc'}, {'args': ['bad\x00arg']}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                decode_request(encode(self.request(**extra)))
        for command in ('bash -c whoami', 'deskharbor-sandbox-v1 AAAA;id'):
            with self.assertRaises(ValueError):
                decode_request(command)

    def test_external_worktrees_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'project'
            root.mkdir()
            (root / '.git').write_text('gitdir: /elsewhere')
            with self.assertRaises(ValueError):
                checked_project({'host_path': str(root)})

    def test_ssh_connection_has_no_forwarding_and_requires_pinned_host_key(self):
        config = {'host': '192.0.2.10', 'user': 'deskharbor',
                  'identity_file': '/key', 'known_hosts': '/known'}
        command = connection(config, 'opaque')
        self.assertIn('ClearAllForwardings=yes', command)
        self.assertIn('StrictHostKeyChecking=yes', command)
        config['host'] = '-oProxyCommand=evil'
        with self.assertRaises(ValueError):
            connection(config, 'opaque')


if __name__ == '__main__':
    unittest.main()
