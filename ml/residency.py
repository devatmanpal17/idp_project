"""Playback-driven Ollama residency with budget and dwell hysteresis."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from threading import Event, RLock, Thread

log = logging.getLogger(__name__)
STATES = {'PLAYING', 'PAUSED', 'SEEKING', 'HIDDEN', 'ENDED'}


def canonical_model(name):
    return name if ':' in name.rsplit('/', 1)[-1] else f'{name}:latest'


class OllamaTransport:
    def __init__(self):
        self.base = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')

    def ps(self):
        with urllib.request.urlopen(f'{self.base}/api/ps', timeout=3) as response:
            return json.load(response).get('models', [])

    def control(self, model, keep_alive, embed=False):
        endpoint = 'embed' if embed else 'generate'
        payload = {'model': model, 'keep_alive':
                   -1 if keep_alive == '-1' else 0 if keep_alive == '0' else keep_alive}
        payload['input' if embed else 'prompt'] = ''
        if not embed:
            payload['stream'] = False
        request = urllib.request.Request(f'{self.base}/api/{endpoint}',
            data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)


class ResidencyController:
    def __init__(self, transport=None, clock=None):
        self.transport = transport or OllamaTransport()
        self.clock = clock or time.monotonic
        self.lock = RLock()
        self.state = 'PAUSED'
        self.state_since = self.clock()
        self.last_action = float('-inf')
        self.budget_mb = int(os.getenv('C_RAM_BUDGET_MB', '8192'))
        self.play_dwell = float(os.getenv('C_PLAY_DWELL_S', '30'))
        self.hidden_dwell = float(os.getenv('C_HIDDEN_S', '60'))
        self.cooldown = float(os.getenv('C_COOLDOWN_S', '5'))
        self.llm = os.getenv('OLLAMA_CHAT_MODEL', 'llama3.2:3b')
        self.embedder = os.getenv('OLLAMA_EMBED_MODEL', 'embeddinggemma')
        self.default_keep_alive = os.getenv('C_DEFAULT_KEEP_ALIVE', '10m')
        self.enabled = True
        self.player_active = False
        self.loads = 0
        self.unloads = 0
        self.pins = 0
        self.last_resident_mb = 0.0
        self.pinned = set()
        self.requested_pins = set()
        self.retired = set()

    def set_chat_model(self, model):
        with self.lock:
            previous = canonical_model(self.llm)
            self.llm = model
            current = canonical_model(model)
            self.retired.discard(current)
            if (previous != current and previous != canonical_model(self.embedder)
                    and previous in (self.pinned | self.requested_pins)):
                self.retired.add(previous)

    def keep_alive(self, model):
        with self.lock:
            if not self.enabled or not self.player_active:
                return self.default_keep_alive
            name = canonical_model(model)
            if name not in {canonical_model(self.llm), canonical_model(self.embedder)}:
                return self.default_keep_alive
            if self.state == 'HIDDEN' and self.clock() - self.state_since >= self.hidden_dwell:
                return self.default_keep_alive
            if name == canonical_model(self.llm) and self.state == 'PLAYING' and self.clock() - self.state_since >= self.play_dwell:
                return self.default_keep_alive
            # Requests may pin before the worker's next residency sample. Keep
            # that intent so a rapid configuration switch can retire the pin.
            self.requested_pins.add(name)
            return -1

    def _act(self, model, keep_alive, loaded=False):
        self.transport.control(model, keep_alive,
                               embed=canonical_model(model) == canonical_model(self.embedder))
        if keep_alive == '0':
            self.unloads += 1
            self.pinned.discard(canonical_model(model))
            self.requested_pins.discard(canonical_model(model))
        else:
            if loaded:
                self.pins += 1
            else:
                self.loads += 1
            if keep_alive == '-1':
                self.pinned.add(canonical_model(model))
        self.last_action = self.clock()

    def request_completed(self, model, keep_alive):
        """A switched-away request may finish after the worker retired its pin."""
        if keep_alive != -1:
            return
        with self.lock:
            name = canonical_model(model)
            self.requested_pins.add(name)
            if name not in {canonical_model(self.llm), canonical_model(self.embedder)}:
                self.retired.add(name)

    def transition(self, state):
        if state not in STATES:
            raise ValueError('Invalid player state.')
        with self.lock:
            self.player_active = True
            if state != self.state:
                self.state, self.state_since = state, self.clock()
            return self.tick()

    def tick(self):
        with self.lock:
            if not self.player_active:
                return self.status()
            try:
                models = self.transport.ps()
                self.enabled = True
                resident = {canonical_model(item.get('name', item.get('model', ''))): item for item in models}
                self.pinned.intersection_update(resident)
                llm_key, embed_key = canonical_model(self.llm), canonical_model(self.embedder)
                self.last_resident_mb = sum(int(item.get('size', 0)) for item in models) / (1024 * 1024)
                if self.clock() - self.last_action < self.cooldown:
                    return self.status()
                for name in sorted(self.retired):
                    if name not in resident:
                        self.retired.discard(name)
                        self.requested_pins.discard(name)
                        continue
                    self._act(name, '0')
                    self.retired.discard(name)
                    return self.status()
                if self.state in ('PAUSED', 'ENDED'):
                    # Evict unrelated models before making room for the assistant.
                    for name in list(resident):
                        if name not in (llm_key, embed_key) and self.last_resident_mb > self.budget_mb:
                            self._act(name, '0')
                            return self.status()
                    if llm_key not in resident:
                        self._act(self.llm, '-1')
                    elif llm_key not in self.pinned:
                        self._act(self.llm, '-1', loaded=True)
                    elif embed_key not in resident or embed_key not in self.pinned:
                        self._act(self.embedder, '-1', loaded=embed_key in resident)
                elif self.state == 'PLAYING':
                    if embed_key not in resident or embed_key not in self.pinned:
                        self._act(self.embedder, '-1', loaded=embed_key in resident)
                    elif self.clock() - self.state_since >= self.play_dwell and self.last_resident_mb > self.budget_mb and llm_key in resident:
                        self._act(self.llm, '0')
                elif self.state == 'HIDDEN' and self.clock() - self.state_since >= self.hidden_dwell:
                    if llm_key in resident:
                        self._act(self.llm, '0')
                    elif embed_key in resident:
                        self._act(self.embedder, '0')
                return self.status()
            except Exception as exc:
                log.warning('Ollama residency control unavailable: %s', exc)
                self.enabled = False
                return self.status()

    def status(self):
        return {'state': self.state, 'enabled': self.enabled,
                'player_active': self.player_active,
                'resident_mb': self.last_resident_mb,
                'loads': self.loads, 'unloads': self.unloads, 'pins': self.pins}


residency = ResidencyController()


def start_residency_worker():
    stop = Event()

    def run():
        while not stop.wait(5):
            residency.tick()

    thread = Thread(target=run, name='ollama-residency', daemon=True)
    thread.start()
    return stop
