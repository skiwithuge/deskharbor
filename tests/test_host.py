"""Host contracts using temporary profiles; never access the live Docker daemon."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from deskharbor import actions, config, tui


class FakeUI:
    def __init__(self, answers, secret='new12345'):
        self.answers = iter(answers)
        self.password = secret
    def menu(self, *args, **kwargs): return next(self.answers)
    def message(self, *args): pass
    def secret(self, *args): return self.password


class HostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.c = config.defaults()
        self.c.update(uid=1000, gid=1000, projects=str(self.root / 'projects'))
    def tearDown(self): self.temp.cleanup()
    def model(self, c=None): return config.compose(self.root, c or self.c)

    def test_missing_or_malformed_config_has_readable_errors(self):
        for value in ([], {'version': 1}, {**self.c, 'ports': []}, {**self.c, 'mounts': ['bad']}):
            with self.assertRaises(ValueError): config.validate(value)

    def test_cpu_local_minimal_default(self):
        model = self.model(); service = model['services']['workstation']
        self.assertNotIn('deploy', service)
        self.assertEqual(service['environment']['NVIDIA_VISIBLE_DEVICES'], 'void')
        self.assertEqual(service['build']['args']['BASE_IMAGE'], 'ubuntu:24.04')
        self.assertEqual(service['ports'], ['127.0.0.1:6080:6080', '127.0.0.1:20222:22'])
        self.assertEqual(service['environment']['ENABLE_AUDIO'], 'false')
        self.assertEqual(service['environment']['ENABLE_VNC'], 'true')
        self.assertFalse(self.c['mounts'])

    def test_gpu_adds_only_explicit_reservation(self):
        self.c['features']['gpu'] = True
        service = self.model()['services']['workstation']
        self.assertEqual(service['build']['args']['BASE_IMAGE'], self.c['cuda_image'])
        self.assertEqual(service['environment']['NVIDIA_VISIBLE_DEVICES'], 'all')
        self.assertEqual(service['deploy']['resources']['reservations']['devices'][0]['capabilities'], ['gpu'])

    def test_key_auth_mounts_public_file_readonly(self):
        service = self.model()['services']['workstation']
        mount = next(m for m in service['volumes'] if m['target'].endswith('/authorized_keys'))
        self.assertTrue(mount['read_only'])
        self.assertNotIn('ssh_password', service['secrets'])

    def test_password_auth_uses_secret_not_environment(self):
        self.c['ssh_auth'] = 'password'
        model = self.model(); service = model['services']['workstation']
        self.assertIn('ssh_password', model['secrets'])
        self.assertNotIn('PASSWORD', ''.join(service['environment']))
        self.assertFalse(any(m['target'].endswith('/authorized_keys') for m in service['volumes']))

    def test_native_only_and_audio_dependencies(self):
        self.c['features'].update(browser=False, vnc=True)
        env = self.model()['services']['workstation']['environment']
        self.assertEqual(env['ENABLE_WEB'], 'false')
        self.assertEqual(env['ENABLE_VNC'], 'true')
        self.c['features'].update(vnc=False, audio=True)
        with self.assertRaisesRegex(ValueError, 'Audio requires'): config.validate(self.c)

    def test_no_access_rejected(self):
        self.c['features'] = dict.fromkeys(config.FEATURES, False)
        with self.assertRaisesRegex(ValueError, 'at least'): config.validate(self.c)

    def test_disabling_preserves_named_volumes(self):
        initial = self.model()['volumes']
        self.c['features'].update(browser=False, ssh=True, audio=False)
        self.assertEqual(initial, self.model()['volumes'])

    def test_ports_overlap_and_mismatched_range_rejected(self):
        self.c['extra_ports'] = [{'host': '6080', 'container': '3000'}]
        with self.assertRaisesRegex(ValueError, 'overlap'): config.validate(self.c)
        self.c['extra_ports'] = [{'host': '3000-3010', 'container': '3000-3005'}]
        with self.assertRaisesRegex(ValueError, 'equal lengths'): config.validate(self.c)

    def test_untyped_boolean_and_root_uid_rejected(self):
        self.c['features']['gpu'] = 'false'
        with self.assertRaises(ValueError): config.validate(self.c)
        self.c['features']['gpu'] = False; self.c['uid'] = 0
        with self.assertRaises(ValueError): config.validate(self.c)

    def test_bind_requires_ipv4(self):
        self.c['bind'] = 'example.invalid'
        with self.assertRaises(ValueError): config.validate(self.c)

    def test_compose_escapes_literal_dollar(self):
        self.c['projects'] = str(self.root / '$project')
        model = self.model()
        self.assertIn('$$project', model['services']['workstation']['volumes'][3]['source'])

    def test_private_files_and_password_validation(self):
        config.save(self.root, self.c)
        path = self.root / '.deskharbor/config.json'
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        config.store_password(self.root, 'vnc_password', 'test1234')
        secret = self.root / '.deskharbor/secrets/vnc_password'
        self.assertEqual(secret.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('test1234', json.dumps(self.model()))
        for value in ('tiny', 'ninechars', 'éééééé'):
            with self.assertRaises(ValueError): config.store_password(self.root, 'vnc_password', value)

    def test_private_key_cannot_be_imported_as_public_key(self):
        key = self.root / 'private'; key.write_text('-----BEGIN OPENSSH PRIVATE KEY-----\nfixture\n')
        with self.assertRaisesRegex(ValueError, 'public-key'): config.store_public_key(self.root, key)
        self.assertFalse((self.root / '.deskharbor/authorized_keys').exists())

    def test_existing_config_is_not_mutated_by_render(self):
        before = copy.deepcopy(self.c)
        config.render(self.root, self.c)
        self.assertEqual(self.c, before)

    def old(self):
        old = self.root / 'old'; old.mkdir()
        (old / 'compose.yaml').write_text('name: old-workstation\n')
        (old / '.env').write_text('USER_NAME=exampleuser\nUSER_UID=1001\nUSER_GID=1001\nPROJECTS_PATH=/srv/projects\nBIND_ADDRESS=0.0.0.0\nCOMPOSE_FILE=compose.yaml:compose.settings.yaml\nHOST_SETTINGS_HOME=/home/exampleuser\n')
        (old / 'secrets').mkdir()
        for name in ('vnc_password', 'ssh_password'): (old / 'secrets' / name).write_text('original-fixture\n')
        return old

    def test_import_preserves_identity_mounts_ports_and_required_volumes(self):
        c = config.legacy(self.root, self.old())
        self.assertTrue(c['adopted']); self.assertEqual(c['uid'], 1001)
        self.assertEqual(c['project_name'], 'old-workstation')
        self.assertEqual(c['bind'], '0.0.0.0')
        self.assertEqual(len(c['mounts']), 5)
        self.assertEqual(len(c['extra_ports']), 3)
        self.assertIn('sublime-text', c['extra_apt_packages'])
        model = config.compose(self.root, c)
        for name, volume in model['volumes'].items():
            self.assertTrue(volume['external']); self.assertEqual(volume['name'], 'old-workstation_' + name)
        self.assertEqual((self.root / '.deskharbor/secrets/vnc_password').read_text(), 'original-fixture\n')

    def test_import_missing_secret_leaves_no_half_profile(self):
        old = self.old(); (old / 'secrets/ssh_password').unlink()
        with self.assertRaises(ValueError): config.legacy(self.root, old)
        self.assertFalse((self.root / '.deskharbor').exists())

    def test_import_cannot_overwrite_profile(self):
        old = self.old(); config.save(self.root, self.c)
        before = (self.root / '.deskharbor/config.json').read_bytes()
        with self.assertRaises(ValueError): config.legacy(self.root, old)
        self.assertEqual((self.root / '.deskharbor/config.json').read_bytes(), before)

    def test_env_is_never_executed(self):
        path = self.root / '.env'
        marker = self.root / 'should-not-exist'
        path.write_text('VALUE=$(touch ' + str(marker) + ')\n')
        self.assertIn('$(', config.parse_env(path)['VALUE'])
        self.assertFalse(marker.exists())

    def test_cancel_credentials_keeps_original_file(self):
        config.store_password(self.root, 'vnc_password', 'test1234')
        original = copy.deepcopy(self.c)
        ui = FakeUI(['credentials', 'vnc', 'back', 'back'])
        self.assertIsNone(tui.settings(ui, self.root, self.c))
        self.assertEqual((self.root / '.deskharbor/secrets/vnc_password').read_text(), 'test1234')
        self.assertEqual(self.c, original)

    def test_save_applies_staged_credentials(self):
        ui = FakeUI(['credentials', 'vnc', 'back', 'save'])
        tui.settings(ui, self.root, self.c)
        self.assertEqual((self.root / '.deskharbor/secrets/vnc_password').read_text(), 'new12345')

    def test_audio_selection_enables_its_desktop_dependency(self):
        self.c['features']['browser'] = False
        c = tui.settings(FakeUI(['features', 'audio', 'back', 'save']), self.root, self.c)
        self.assertTrue(c['features']['browser']); self.assertTrue(c['features']['audio'])

    def test_stop_never_removes_volumes(self):
        with patch.object(actions, 'host_required'), patch.object(actions, 'run') as call:
            actions.perform(self.root, 'stop', self.c)
        argv = call.call_args.args[0]
        self.assertEqual(argv[-1], 'stop'); self.assertNotIn('down', argv)
        self.assertNotIn('-v', argv)

    def test_missing_adopted_volume_refuses_start(self):
        self.c['adopted'] = True
        (self.root / '.deskharbor').mkdir(); (self.root / '.deskharbor/authorized_keys').write_text('fixture')
        config.store_password(self.root, 'vnc_password', 'test1234')
        def execute(argv, **kwargs):
            if argv[1:3] == ['volume', 'inspect']: raise subprocess.CalledProcessError(1, argv)
        with patch.object(actions, 'host_required'), patch.object(actions, 'run', side_effect=execute):
            with self.assertRaisesRegex(ValueError, 'Refusing an empty replacement'):
                actions.prerequisites(self.root, self.c)


if __name__ == '__main__': unittest.main()
