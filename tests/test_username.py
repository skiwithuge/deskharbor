"""Username selection uses the existing Docker identity and persistence model."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from deskharbor import actions, config, tui


class UsernameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def ui(self, names, choice='save'):
        ui = Mock()
        ui.input.side_effect = [*names, str(self.root / 'projects'), 'password']
        ui.secret.side_effect = ['test1234', 'fixture-ssh-secret']
        ui.menu.return_value = choice
        return ui

    def test_custom_user_reaches_image_and_mount_paths(self):
        c = tui.setup(self.ui(['developer']), self.root)
        self.assertEqual(config.load(self.root)['username'], 'developer')
        service = config.compose(self.root, c)['services']['workstation']
        self.assertEqual(service['build']['args']['USER_NAME'], 'developer')
        self.assertEqual(service['volumes'][0]['target'], '/home/developer')
        self.assertTrue(any(m['target'] == '/home/developer/projects' for m in service['volumes']))
        self.assertIn('Workstation user: developer', actions.plan(c))

    def test_default_name_is_preserved(self):
        c = tui.setup(self.ui(['deskharbor']), self.root)
        self.assertEqual(c['username'], 'deskharbor')

    def test_invalid_names_retry_before_saving(self):
        ui = self.ui(['root', 'Invalid Name', 'dev_user'])
        c = tui.setup(ui, self.root)
        self.assertEqual(c['username'], 'dev_user')
        self.assertEqual(ui.message.call_count, 2)

    def test_cancel_keeps_new_identity_and_credentials_unsaved(self):
        self.assertIsNone(tui.setup(self.ui(['developer'], 'back'), self.root))
        self.assertFalse((self.root / '.deskharbor').exists())

    def test_existing_profile_preserves_user_and_volumes(self):
        c = config.defaults()
        c.update(username='existing_user', uid=1000, gid=1000)
        config.save(self.root, c)
        ui = Mock()
        ui.menu.return_value = 'save'
        saved = tui.settings(ui, self.root, c)
        self.assertEqual(saved, c)
        self.assertIn('existing_user', ui.menu.call_args.args[2])
        ui.input.assert_not_called()

    def test_username_validation_rejects_invalid_and_root_names(self):
        for value in ('root', '', 'Somebody', 'with space', '-invalid', '123user', 'a' * 32, 'éclair'):
            with self.subTest(value=value):
                c = config.defaults()
                c.update(username=value, uid=1000, gid=1000)
                with self.assertRaises(ValueError):
                    config.validate(c)


if __name__ == '__main__':
    unittest.main()
