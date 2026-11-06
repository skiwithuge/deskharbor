# Testing

Host unit checks (Python 3 standard library):

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

These use temporary profiles and synthetic credentials/projects. They do not inspect or start the live workstation.

On a Linux Docker host, build a test image with the default `deskharbor` username (`docker build -t deskharbor:test .`) and run `tests/smoke.sh deskharbor:test`. The shell smoke fixtures assume that default username; do not use a customized/adopted user image. CPU mode is the default. Set `DESKHARBOR_TEST_GPU=1` to request NVIDIA access and execute CUDA checks against a CUDA-enabled image. Test containers use isolated volumes and temporary test passwords; they must not point at production volumes/settings. Other feature/install checks are in `tests/` and require Docker plus network access for publisher downloads.

`python3 tests/audio.py` tests real PulseAudio capture and HTTP PCM/MP3 playback with a generated tone in a private temporary audio server. It requires PulseAudio, pactl and FFmpeg. `tests/desktop-boot.py` starts GNOME on a private display and requires the image's custom session; it does not restart the active desktop.

Sandbox policy tests:

```bash
python3 -m venv /tmp/deskharbor-test
/tmp/deskharbor-test/bin/pip install -r sandbox/requirements.txt
cd sandbox
/tmp/deskharbor-test/bin/python -m unittest discover -s tests -v
```

These require libfuse and local Unix sockets. FUSE/kernel, sibling-container and authenticated agent integrations are separate checks documented in `sandbox/README.md`. Passing policy tests does not validate every host security policy or agent login/model session.

`/usr/bin/python3 tests/service-config.py` parses all supported service-activation combinations through the actual Supervisor parser; run it inside a test image or an environment with Supervisor installed.
