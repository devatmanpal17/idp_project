"""Own and supervise the Render-only processes; never used by start_all.bat."""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
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
    if not 1024 <= port <= 65535 or port in (3000, 8000, 11434, 18012, 18013, 19099):
        raise ValueError('PORT must be 1024..65535, excluding internal and Render-reserved ports.')
    return port


def validate_password(password: str) -> None:
    # bcrypt has a 72-byte password limit; ASCII keeps characters and bytes equal.
    if not 16 <= len(password) <= 72 or any(not 32 <= ord(c) <= 126 for c in password):
        raise ValueError('CHAI_HOST_PASSWORD must contain 16..72 printable ASCII characters.')


def runtime_environment(source: dict[str, str]) -> dict[str, str]:
    env = {key: value for key, value in source.items() if key != 'CHAI_HOST_PASSWORD'}
    data = PurePosixPath('/var/data')
    # These paths are deployment-only; local .env and data directories are untouched.
    env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_BASE_URL='http://127.0.0.1:11434',
               OLLAMA_MODELS=str(data/'ollama'), CHROMA_PERSIST_DIR=str(data/'chroma'),
               NITRO_HOST='127.0.0.1', NITRO_PORT='3000', NODE_ENV='production')
    defaults = dict(DATABASE_URL=f'sqlite:///{data}/analytics.sqlite3',
                    OLLAMA_EMBED_MODEL='embeddinggemma', OLLAMA_CHAT_MODEL='llama3.2:3b',
                    OLLAMA_NUM_PARALLEL='1', OLLAMA_MAX_LOADED_MODELS='2',
                    OLLAMA_CONTEXT_LENGTH='4096', C_RAM_BUDGET_MB='6144',
                    CHAI_MODEL_AUTO_PULL='true')
    for key, default in defaults.items():
        env[key] = env.get(key, '').strip() or default
    if env['DATABASE_URL'].startswith('sqlite'):
        # A copied localhost URL or in-memory database would lose data on redeploy.
        path = env['DATABASE_URL'].partition(':///')[2].split('?', 1)[0]
        target = PurePosixPath(path)
        if not path or not target.is_absolute() or not target.is_relative_to(data) or '..' in target.parts:
            raise ValueError('Hosted SQLite DATABASE_URL must point inside /var/data.')
    if env.get('CHROMA_HOST', '').strip():
        raise ValueError('This Blueprint uses persistent local Chroma; remove CHROMA_HOST.')
    for key in ('OLLAMA_NUM_PARALLEL', 'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_CONTEXT_LENGTH', 'C_RAM_BUDGET_MB'):
        if not env[key].isdigit() or int(env[key]) < 1:
            raise ValueError(f'{key} must be a positive integer.')
    if env['CHAI_MODEL_AUTO_PULL'].lower() not in ('true', 'false'):
        raise ValueError('CHAI_MODEL_AUTO_PULL must be true or false.')
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
        self.models_ready = threading.Event()
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
                        payload = json.load(response)
                    if not isinstance(payload, dict) or not isinstance(payload.get('models'), list):
                        raise ValueError('Invalid model inventory.')
                    names = set()
                    for item in payload['models']:
                        if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not isinstance(item.get('digest'), str) or not item['digest']:
                            raise ValueError('Invalid model inventory entry.')
                        names.add(item['name'])
                    canonical = model if ':' in model.rsplit('/', 1)[-1] else model + ':latest'
                    if canonical in names:
                        break
                    if self.env['CHAI_MODEL_AUTO_PULL'].lower() != 'true':
                        self.stop.wait(5)
                        continue
                    process = self.launch('Model download', ['ollama', 'pull', model], critical=False)
                    while process.poll() is None and not self.stop.wait(.5):
                        pass
                    if process.returncode == 0:
                        # Check the committed manifest, rather than trusting CLI exit alone.
                        continue
                    print('Model download failed; retrying in 30 seconds.', flush=True)
                except (OSError, ValueError, KeyError, RuntimeError):
                    if self.stop.is_set():
                        return
                    print('Model setup is temporarily unavailable; retrying.', flush=True)
                self.stop.wait(30)
        if not self.stop.is_set():
            self.models_ready.set()
            print('Required Ollama models are available.', flush=True)

    def retire(self, name: str):
        """Replace the read-only setup API before opening the persistent vector store."""
        with self.lock:
            selected = [entry for entry in self.children if entry[0] == name]
            self.children = [entry for entry in self.children if entry[0] != name]
        for _, child, _ in selected:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()

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
    if env['DATABASE_URL'].startswith('sqlite'):
        Path(env['DATABASE_URL'].partition(':///')[2].split('?', 1)[0]).parent.mkdir(parents=True, exist_ok=True)
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
        # Restarted SQL jobs can resume during API lifespan startup. Make their
        # inference transport available before that startup begins.
        services.ready('http://127.0.0.1:11434/api/tags')
        # Opening RAG before the first model download records an unresolved model
        # identity. The next restart would invalidate its patent vectors. A small
        # read-only API keeps platform probes and setup status available meanwhile.
        services.launch('Setup API', [sys.executable, '-m', 'uvicorn', 'deploy.render.setup_api:app',
                                     '--host', '127.0.0.1', '--port', '8000'])
        services.launch('Dashboard', ['node', 'frontend/dist-render/server/index.mjs'])
        services.ready('http://127.0.0.1:8000/api/live')
        services.ready('http://127.0.0.1:3000/')
        services.launch('Gateway', ['nginx', '-c', str(config), '-g', 'daemon off;'])
        threading.Thread(target=services.bootstrap_models, daemon=True).start()
        api_started = False
        while not services.stop.wait(.5):
            if services.failures():
                raise RuntimeError(f'A required process exited: {services.failures()}')
            if services.models_ready.is_set() and not api_started:
                services.retire('Setup API')
                services.launch('API', [sys.executable, '-m', 'uvicorn', 'backend.app:app',
                                       '--host', '127.0.0.1', '--port', '8000', '--workers', '1',
                                       '--timeout-graceful-shutdown', '80'])
                services.ready('http://127.0.0.1:8000/api/live')
                api_started = True
        return 0
    finally:
        services.close()


if __name__ == '__main__':
    raise SystemExit(main())
