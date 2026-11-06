#!/usr/bin/env python3
"""Exercise real virtual audio, HTTP authentication, encoding and disconnect cleanup."""
import base64
import http.client
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('audio_server', ROOT / 'scripts/audio-server.py')
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def wait_for(predicate, message):
    for _ in range(60):
        if predicate():
            return
        time.sleep(.1)
    raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix='deskharbor-audio-test-') as temporary:
    root = Path(temporary)
    runtime = root / 'runtime'
    runtime.mkdir(mode=0o700)
    home = root / 'home'
    home.mkdir()
    os.environ.update(XDG_RUNTIME_DIR=str(runtime), HOME=str(home),
                      PULSE_SERVER='unix:' + str(runtime / 'pulse/native'))
    password = root / 'password'
    password.write_text('test1234')
    auth_path = root / 'auth.json'
    audio.prepare_auth(password, auth_path, 'testuser')
    record = json.loads(auth_path.read_text())
    check(auth_path.stat().st_mode & 0o777 == 0o600, 'Auth verifier must be private')
    check('test1234' not in auth_path.read_text(), 'Plaintext password persisted')
    token = 'Basic ' + base64.b64encode(b'testuser:test1234').decode()
    for bad in ('', 'Bearer value', 'Basic invalid', 'Basic /w==',
                'Basic ' + base64.b64encode(b'testuser:wrong').decode()):
        check(not audio.authorized(bad, record), 'Invalid authentication accepted')
    pulse = tone = server = None
    with (root / 'pulse.log').open('w') as log:
        try:
            pulse = subprocess.Popen(['pulseaudio', '--daemonize=no', '--exit-idle-time=-1',
                                      '--high-priority=no', '--realtime=no', '-n',
                                      '--file=' + str(ROOT / 'config/audio/pulse.pa')],
                                     stdout=log, stderr=log)
            wait_for(lambda: (runtime / 'pulse/native').exists(), 'PulseAudio did not start')
            result = subprocess.run(['pactl', 'list', 'short', 'sinks'], capture_output=True, check=True)
            check(b'workstation' in result.stdout, 'Missing virtual sink')
            server = audio.AudioServer(('127.0.0.1', 0), record, ROOT / 'config/audio', 'workstation.monitor')
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            port = server.server_address[1]

            def request(path, authorization=token, **headers):
                client = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
                if authorization:
                    headers['Authorization'] = authorization
                client.request('GET', path, headers=headers)
                return client, client.getresponse()

            for path in ('/', '/stream.mp3', '/stream.pcm', '/health', '/audio.js'):
                client, response = request(path, authorization='')
                check(response.status == 401, 'Unauthenticated audio accessible: ' + path)
                response.read(); client.close()
            client, response = request('/stream.mp3', **{'Sec-Fetch-Site': 'cross-site'})
            check(response.status == 403, 'Cross-site audio embedding accepted')
            response.read(); client.close()
            for path in ('/', '/audio.js', '/audio.css', '/health'):
                client, response = request(path)
                check(response.status == 200, 'Audio route unavailable: ' + path)
                check(response.getheader('Cache-Control') == 'no-store', 'Audio responses cached')
                response.read(); client.close()
            print('PASS: private auth verifier, authentication, cross-site rejection, page and health')

            # Feed a known signal through PulseAudio: never record real desktop audio.
            tone = subprocess.Popen(['ffmpeg', '-nostdin', '-loglevel', 'error', '-re',
                                     '-f', 'lavfi', '-i', 'sine=frequency=523:sample_rate=48000',
                                     '-t', '30', '-f', 'pulse', 'workstation'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            client, response = request('/stream.mp3')
            check(response.status == 200, 'Stream failed')
            check(response.getheader('Content-Type') == 'audio/mpeg', 'Wrong media type')
            encoded = response.read(32768)
            response.close(); client.close()
            check(len(encoded) == 32768, 'No encoded audio')
            decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', 'pipe:0', '-f', 's16le',
                                      '-ac', '1', '-ar', '48000', 'pipe:1'], input=encoded,
                                     capture_output=True, timeout=10, check=True).stdout
            values = struct.unpack('<' + 'h' * (len(decoded) // 2), decoded)
            rms = math.sqrt(sum(x*x for x in values) / max(1, len(values)))
            check(rms > 300, 'Encoded stream is silent despite test tone')
            # Count crossings to distinguish the intended tone from noise.
            tail = values[-24000:]
            frequency = sum(a <= 0 < b for a, b in zip(tail, tail[1:])) * 48000 / len(tail)
            check(abs(frequency - 523) < 10, 'Test tone was not preserved')
            wait_for(lambda: server.listeners._value == 2, 'Disconnected encoder leaked')
            print('PASS: virtual sink → HTTP MP3 → decoded 523 Hz tone; encoder cleaned up')

            client, response = request('/stream.pcm')
            check(response.status == 200, 'PCM stream failed')
            raw = response.read(48000 * 4)
            response.close(); client.close()
            samples = struct.unpack('<' + 'h' * (len(raw) // 2), raw)[::2]
            rms = math.sqrt(sum(x*x for x in samples) / len(samples))
            check(rms > 300, 'PCM stream lost the generated signal')
            wait_for(lambda: server.listeners._value == 2, 'PCM encoder leaked')
            print('PASS: live PCM contains the test signal; disconnect cleaned up')

            # At most two simultaneous streams; a third cannot spawn an encoder.
            held = [request('/stream.mp3') for _ in range(2)]
            client, response = request('/stream.mp3')
            check(response.status == 503, 'Listener limit not enforced')
            response.read(); client.close()
            for client, response in held:
                response.close(); client.close()
            wait_for(lambda: server.listeners._value == 2, 'Listener slots leaked')
            print('PASS: listener limit and reconnect cleanup')
        finally:
            if server:
                server.shutdown(); server.server_close()
            for process in (tone, pulse):
                if process:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait()
