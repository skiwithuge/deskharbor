"""Exercise browser launch selection without opening Chrome or accessing a GPU."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BrowserLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        chrome = self.bin / 'chrome-real'
        chrome.write_text('#!' + sys.executable + '\nimport json,os,sys\nprint(json.dumps({"args":sys.argv[1:],"software":os.environ.get("LIBGL_ALWAYS_SOFTWARE")}))\n')
        chrome.chmod(0o755)
        for name, content in {
            'nvidia-smi': '#!/bin/sh\n[ "$FAKE_GPU" = yes ]\n',
            'ldconfig': '#!/bin/sh\nif [ "$FAKE_GRAPHICS" = yes ]; then echo "libGLX_nvidia.so.0 => /fake/library"; fi\n',
        }.items():
            path = self.bin / name
            path.write_text(content)
            path.chmod(0o755)
        self.launcher = self.root / 'browser.sh'
        self.launcher.write_text((ROOT / 'scripts/browser.sh').read_text().replace('/usr/bin/google-chrome-stable', str(chrome)))
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        FAKE_GPU='no', FAKE_GRAPHICS='yes', LIBGL_ALWAYS_SOFTWARE='1')
        self.env.pop('DESKHARBOR_BROWSER_RENDERER', None)

    def tearDown(self):
        self.temp.cleanup()

    def launch(self, *args):
        return subprocess.run(['bash', str(self.launcher), *args], env=self.env, text=True, capture_output=True)

    def test_cpu_keeps_existing_launch_behavior(self):
        result = self.launch('http://localhost:3000')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertNotIn('--use-angle=vulkan', data['args'])
        self.assertEqual(data['software'], '1')

    def test_auto_nvidia_selects_vulkan_and_removes_software_override(self):
        self.env['FAKE_GPU'] = 'yes'
        result = self.launch('http://localhost:3000')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn('--use-angle=vulkan', data['args'])
        self.assertIsNone(data['software'])
        self.assertNotIn('--ignore-gpu-blocklist', data['args'])
        self.assertNotIn('--enable-unsafe-swiftshader', data['args'])

    def test_compute_only_gpu_does_not_enable_graphics_path(self):
        self.env.update(FAKE_GPU='yes', FAKE_GRAPHICS='no')
        data = json.loads(self.launch().stdout)
        self.assertNotIn('--use-angle=vulkan', data['args'])

    def test_explicit_nvidia_missing_gpu_fails_before_chrome(self):
        self.env['DESKHARBOR_BROWSER_RENDERER'] = 'nvidia'
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)
        self.assertIn('NVIDIA', result.stderr)

    def test_explicit_software_preserves_cpu_mode_even_with_gpu(self):
        self.env.update(FAKE_GPU='yes', DESKHARBOR_BROWSER_RENDERER='software')
        data = json.loads(self.launch().stdout)
        self.assertNotIn('--use-angle=vulkan', data['args'])
        self.assertEqual(data['software'], '1')

    def test_invalid_mode_is_explained_without_launch(self):
        self.env['DESKHARBOR_BROWSER_RENDERER'] = 'unknown'
        result = self.launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(result.stdout)
        self.assertIn('auto', result.stderr)

    def test_browser_arguments_remain_separate(self):
        self.env['FAKE_GPU'] = 'yes'
        args = ['--user-data-dir=/tmp/profile with spaces', 'http://localhost:3000/?a=1&b=2']
        data = json.loads(self.launch(*args).stdout)
        self.assertEqual(data['args'][-2:], args)


if __name__ == '__main__':
    unittest.main()
