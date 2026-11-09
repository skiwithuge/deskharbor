"""Log interruption returns to the host menu without stopping the workstation."""
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from deskharbor import actions, config, tui


class LogMenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        c = config.defaults()
        c.update(uid=1000, gid=1000, projects=str(self.root / 'projects'))
        config.save(self.root, c)

    def tearDown(self):
        self.temp.cleanup()

    def check_return_to_menu(self, interruption):
        ui = Mock()
        ui.menu.side_effect = ['logs', 'status', 'exit']
        with patch.object(tui, 'UI', return_value=ui), \
             patch.object(actions, 'perform', side_effect=[interruption, None]) as perform, \
             patch('builtins.input', return_value=''):
            tui.main(self.root)
        self.assertEqual([call.args[1] for call in perform.call_args_list], ['logs', 'status'])
        self.assertFalse(any(call.args[0] == 'Operation failed' for call in ui.menu.call_args_list))

    def test_ctrl_c_returns_to_menu(self):
        self.check_return_to_menu(KeyboardInterrupt())

    def test_compose_sigint_exit_returns_to_menu(self):
        for code in (-signal.SIGINT, 128 + signal.SIGINT):
            with self.subTest(returncode=code):
                self.check_return_to_menu(subprocess.CalledProcessError(code, ['docker', 'compose', 'logs']))

    def test_actual_log_failure_still_offers_retry(self):
        ui = Mock()
        ui.menu.side_effect = ['logs', 'back', 'exit']
        with patch.object(tui, 'UI', return_value=ui), \
             patch.object(actions, 'perform', side_effect=subprocess.CalledProcessError(1, ['docker', 'compose', 'logs'])):
            tui.main(self.root)
        self.assertTrue(any(call.args[0] == 'Operation failed' for call in ui.menu.call_args_list))

    def test_interrupting_apply_is_not_swallowed(self):
        ui = Mock()
        ui.menu.side_effect = ['up', 'apply']
        with patch.object(tui, 'UI', return_value=ui), \
             patch.object(actions, 'perform', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                tui.main(self.root)


if __name__ == '__main__':
    unittest.main()
