"""Own and supervise the Render-only processes; never used by start_all.bat."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]


def public_port(value: str) -> int:
    port = int(value)
    if not 1024 <= port <= 65535 or port in (3000, 8000, 11434):
        raise ValueError('PORT must be 1024..65535 and distinct from internal ports.')
    return port


def validate_password(password: str) -> None:
    # bcrypt has a 72-byte password limit; ASCII keeps characters and bytes equal.
    if not 16 <= len(password) <= 72 or any(not 32 <= ord(c) <= 126 for c in password):
        raise ValueError('CHAI_HOST_PASSWORD must contain 16..72 printable ASCII characters.')


def runtime_environment(source: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in source.items() if key != 'CHAI_HOST_PASSWORD'}
    data = Path('/var/data')
    # These paths are deployment-only; local .env and data directories are untouched.
    env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_BASE_URL='http://127.0.0.1:11434',
               OLLAMA_MODELS=str(data/'ollama'), CHROMA_PERSIST_DIR=str(data/'chroma'),
               NITRO_HOST='127.0.0.1', NITRO_PORT='3000', NODE_ENV='production')
    env.setdefault('DATABASE_URL', f'sqlite:///{data}/analytics.sqlite3')
    env.setdefault('OLLAMA_EMBED_MODEL', 'embeddinggemma')
    env.setdefault('OLLAMA_CHAT_MODEL', 'llama3.2:3b')
    env.setdefault('OLLAMA_NUM_PARALLEL', '1')
    env.setdefault('OLLAMA_MAX_LOADED_MODELS', '2')
    env.setdefault('OLLAMA_CONTEXT_LENGTH', '4096')
    env.setdefault('C_RAM_BUDGET_MB', '6144')
    external = env.get('RENDER_EXTERNAL_URL', '').strip()
    if external and not env.get('CORS_ORIGINS'):
        parsed = urlsplit(external)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('RENDER_EXTERNAL_URL must be an HTTPS URL without credentials.')
        env['CORS_ORIGINS'] = f'{parsed.scheme}://{parsed.netloc}'
    return env


class Services:
    def __init__(self, env: dict[str, str]):
        self.env = env
        self.stop = threading.Event()
        self.children: list[tuple[str, subprocess.Popen, bool]] = []
        self.lock = threading.Lock()

    def launch(self, name: str, args: list[str], critical: bool = True) -> subprocess.Popen:
        with self.lock:
            if self.stop.is_set():
                raise RuntimeError('Shutdown requested.')
            child = subprocess.Popen(args, cwd=ROOT, env=self.env, start_new_session=True)
            self.children.append((name, child, critical))
        print(f'{name} started.', flush=True)
        return child

    def failures(self):
        with self.lock:
            return [(name, child.returncode) for name, child, critical in self.children
                    if critical and child.poll() is not None]

    def ready(self, url: str, timeout: float = 120):
        deadline = time.monotonic() + timeout
        while not self.stop.is_set() and time.monotonic() < deadline:
            if self.failures():
                raise RuntimeError(f'A required process exited: {self.failures()}')
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status == 200:
                        return
            except (OSError, ValueError):
                pass
            self.stop.wait(.5)
        raise RuntimeError('Service startup was interrupted or timed out.')

    def bootstrap_models(self):
        # First boot downloads models on the mounted disk, never during image build.
        # Missing models keep /api/health at setup_required, without restart loops.
        models = dict.fromkeys((self.env['OLLAMA_EMBED_MODEL'], self.env['OLLAMA_CHAT_MODEL']))
        for model in models:
            while not self.stop.is_set():
                try:
                    with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=3) as response:
                        names = {item['name'] for item in json.load(response).get('models', [])}
                    canonical = model if ':' in model else model + ':latest'
                    if canonical in names:
                        break
                    process = self.launch('Model download', ['ollama', 'pull', model], critical=False)
                    while process.poll() is None and not self.stop.wait(.5):
                        pass
                    if process.returncode == 0:
                        break
                    print('Model download failed; retrying in 30 seconds.', flush=True)
                except (OSError, ValueError, KeyError, RuntimeError):
                    if self.stop.is_set():
                        return
                    print('Model setup is temporarily unavailable; retrying.', flush=True)
                self.stop.wait(30)
        if not self.stop.is_set():
            print('Required Ollama models are available.', flush=True)

    def close(self):
        self.stop.set()
        with self.lock:
            children = list(self.children)
        for name, child, _ in reversed(children):
            if name == 'Ollama':
                continue
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGQUIT if name == 'Gateway' else signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 90
        for name, child, _ in reversed(children):
            if name == 'Ollama':
                # Let API requests drain with their inference dependency alive.
                if child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                timeout = 5
            else:
                timeout = max(.1, deadline-time.monotonic())
            try:
                child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait()


def main() -> int:
    if sys.platform != 'linux':
        raise RuntimeError('Use the Render Docker image. For localhost, run start_all.bat.')
    password = os.environ.pop('CHAI_HOST_PASSWORD', '')
    validate_password(password)
    port = public_port(os.environ.get('PORT', '10000'))
    env = runtime_environment(dict(os.environ))
    Path('/var/data').mkdir(parents=True, exist_ok=True)
    # Password goes over stdin, never command-line arguments or image layers.
    subprocess.run(['htpasswd', '-iBc', '/tmp/chaigaram.htpasswd', 'demo'],
                   input=password+'\n', text=True, capture_output=True, check=True)
    password = ''
    os.chmod('/tmp/chaigaram.htpasswd', 0o640)
    import grp
    os.chown('/tmp/chaigaram.htpasswd', 0, grp.getgrnam('www-data').gr_gid)
    template = (ROOT/'deploy/render/nginx.conf.template').read_text()
    config = Path('/tmp/chaigaram-nginx.conf')
    config.write_text(template.replace('__PORT__', str(port)))
    subprocess.run(['nginx', '-t', '-c', str(config)], check=True)
    services = Services(env)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: services.stop.set())
    try:
        services.launch('Ollama', ['ollama', 'serve'])
        services.launch('API', [sys.executable, '-m', 'uvicorn', 'backend.app:app',
                               '--host', '127.0.0.1', '--port', '8000', '--workers', '1',
                               '--timeout-graceful-shutdown', '80'])
        services.launch('Dashboard', ['node', 'frontend/dist-render/server/index.mjs'])
        services.ready('http://127.0.0.1:11434/api/tags')
        services.ready('http://127.0.0.1:8000/api/live')
        services.ready('http://127.0.0.1:3000/')
        services.launch('Gateway', ['nginx', '-c', str(config), '-g', 'daemon off;'])
        if env.get('CHAI_MODEL_AUTO_PULL', 'true').lower() == 'true':
            threading.Thread(target=services.bootstrap_models, daemon=True).start()
        while not services.stop.wait(.5):
            if services.failures():
                raise RuntimeError(f'A required process exited: {services.failures()}')
        return 0
    finally:
        services.close()


if __name__ == '__main__':
    raise SystemExit(main())
