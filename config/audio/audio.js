'use strict';
const audio = document.querySelector('#audio');
const start = document.querySelector('#start');
const stop = document.querySelector('#stop');
const live = document.querySelector('#live');
const mode = document.querySelector('#mode');
const volume = document.querySelector('#volume');
const status = document.querySelector('#status');
let active = null;

function stopAudio() {
  const previous = active;
  active = null;
  if (previous) {
    previous.abort.abort();
    if (previous.context) previous.context.close().catch(() => {});
  }
  audio.pause();
  audio.removeAttribute('src');
  audio.load();
  stop.disabled = live.disabled = true;
  start.disabled = false;
  status.textContent = 'Audio is off.';
}

async function playPCM(session) {
  // Create/resume during the click, before awaiting any network operation.
  const Context = window.AudioContext || window.webkitAudioContext;
  const context = session.context = new Context({latencyHint: 'interactive', sampleRate: 48000});
  session.gain = context.createGain();
  session.gain.gain.value = Number(volume.value);
  session.gain.connect(context.destination);
  await context.resume();
  const response = await fetch('/stream.pcm', {signal: session.abort.signal, cache: 'no-store'});
  if (!response.ok || !response.body) throw new Error('Audio unavailable');
  const reader = response.body.getReader();
  let pending = new Uint8Array(0);
  let nextTime = context.currentTime;
  try {
    while (active === session) {
      const {value, done} = await reader.read();
      if (done) throw new Error('Audio disconnected');
      const bytes = new Uint8Array(pending.length + value.length);
      bytes.set(pending);
      bytes.set(value, pending.length);
      const frames = Math.floor(bytes.length / 4); // Stereo signed 16-bit little endian.
      pending = bytes.slice(frames * 4);
      if (!frames) continue;
      // Drop overdue network bursts instead of building an unbounded playback queue.
      if (context.state !== 'running' || nextTime > context.currentTime + 0.35) continue;
      const buffer = context.createBuffer(2, frames, 48000);
      const samples = new DataView(bytes.buffer, bytes.byteOffset, frames * 4);
      for (let channel = 0; channel < 2; channel++) {
        const output = buffer.getChannelData(channel);
        for (let frame = 0; frame < frames; frame++) {
          output[frame] = samples.getInt16(frame * 4 + channel * 2, true) / 32768;
        }
      }
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(session.gain);
      source.onended = () => source.disconnect();
      nextTime = Math.max(nextTime, context.currentTime + 0.06);
      source.start(nextTime);
      nextTime += buffer.duration;
      live.disabled = false;
      status.textContent = 'Listening to the workstation.';
    }
  } finally {
    reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

async function startAudio() {
  stopAudio();
  const session = active = {abort: new AbortController()};
  status.textContent = 'Connecting…';
  start.disabled = true;
  stop.disabled = false;
  audio.hidden = mode.value !== 'mp3';
  try {
    if (mode.value === 'pcm') {
      await playPCM(session);
    } else {
      audio.volume = Number(volume.value);
      audio.src = '/stream.mp3?t=' + Date.now();
      await audio.play();
      if (active === session) live.disabled = false;
    }
  } catch (_) {
    if (active !== session) return;
    stopAudio();
    status.textContent = 'Audio disconnected. Try Start audio again, or choose MP3 for compatibility.';
  }
}
start.addEventListener('click', startAudio);
live.addEventListener('click', startAudio);
stop.addEventListener('click', stopAudio);
mode.addEventListener('change', () => { stopAudio(); audio.hidden = mode.value !== 'mp3'; });
volume.addEventListener('input', () => {
  audio.volume = Number(volume.value);
  if (active && active.gain) active.gain.gain.value = Number(volume.value);
});
audio.addEventListener('playing', () => { status.textContent = 'Listening to the workstation.'; });
audio.addEventListener('waiting', () => { if (audio.hasAttribute('src')) status.textContent = 'Buffering…'; });
audio.addEventListener('error', () => {
  if (audio.hasAttribute('src')) {
    stopAudio();
    status.textContent = 'Audio disconnected. Press Start audio to reconnect.';
  }
});
window.addEventListener('pagehide', stopAudio);
