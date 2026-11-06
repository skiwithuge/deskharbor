"""Manager policy-preservation and recovery regression tests, no host mutations."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('deskharbor_wizard', Path(__file__).resolve().parents[1] / 'wizard.py')
wizard = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wizard
spec.loader.exec_module(wizard)

class ManagerTests(unittest.TestCase):
    def test_stale_saved_container_detects_running_workstation(self):
        def command(args):
            if args[1] == 'compose': return 'workstation-id'
            if args[-1] == 'testsandbox': raise ValueError('no such object')
            return '{"running":true,"name":"/deskharbor-workstation-1"}'
        with patch.object(wizard, 'run', side_effect=command):
            self.assertEqual(wizard.detect_container('testsandbox'), 'deskharbor-workstation-1')
            with self.assertRaises(ValueError): wizard.detect_container('testsandbox', explicit=True)

    def test_stopped_saved_container_detects_running_workstation(self):
        def command(args):
            if args[1] == 'compose': return 'running'
            return '{"running":' + ('false' if args[-1] == 'stopped' else 'true') + ',"name":"/workstation"}'
        with patch.object(wizard, 'run', side_effect=command):
            self.assertEqual(wizard.detect_container('stopped'), 'workstation')

    def test_edit_retains_gpu_and_all_exclusions(self):
        settings = wizard.Settings()
        settings.load_project('saved', {'host_path': '/project', 'workstation_path': '/mapped',
                                       'allow_gpu': True, 'hidden_paths': ['config/token.json', 'private']})
        command = settings.registration()
        self.assertTrue(settings.gpu)
        self.assertEqual(command[command.index('--hide') + 1], 'config/token.json')
        self.assertIn('--allow-gpu', command)
        self.assertEqual(command.count('--hide'), 2)
        self.assertEqual(settings.id, 'saved')

    def test_new_projects_default_to_cpu(self):
        self.assertNotIn('--allow-gpu', wizard.Settings().registration())
        self.assertIn('--allow-gpu', wizard.Settings(gpu=True).registration())

    def test_update_never_registers_or_resets_projects(self):
        settings = wizard.Settings(host='host', container='workstation')
        steps = wizard.operation_steps(settings, 'update')
        self.assertEqual(len(steps), 3)
        self.assertTrue(any('setup-host.sh' in str(command) for _, command in steps))
        self.assertFalse(any(wizard.ADMIN in command for _, command in steps))
        self.assertFalse(any('reset' in command for _, command in steps))

    def test_project_edit_skips_build_install_and_integration(self):
        steps = wizard.operation_steps(wizard.Settings(), 'project')
        self.assertEqual(len(steps), 1)
        self.assertIn(wizard.ADMIN, steps[0][1])

    def test_retry_repeats_only_the_failed_step(self):
        calls = []
        results = iter((0, 1, 0))
        def execute(command):
            calls.append(command)
            return next(results)
        class UI:
            def menu(self, *args): return 'retry'
        self.assertEqual(wizard.execute_steps(UI(), [('first', ['a']), ('second', ['b'])], execute), 'done')
        self.assertEqual(calls, [['a'], ['b'], ['b']])

    def test_edit_request_retains_values(self):
        settings = wizard.Settings(project='/unchanged', gpu=True, hidden=['private'])
        class UI:
            def menu(self, *args): return 'edit'
        self.assertEqual(wizard.execute_steps(UI(), [('failure', ['x'])], lambda _: 1), 'edit')
        self.assertEqual(settings.project, '/unchanged')
        self.assertTrue(settings.gpu)
        self.assertEqual(settings.hidden, ['private'])

if __name__ == '__main__': unittest.main()
