"""One-click Windows launcher with readiness checks and owned-process cleanup."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class StartupError(RuntimeError):
    pass


def environment(root=ROOT):
    env = os.environ.copy()
    path = root / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def canonical_model(name):
    return name if ':' in name.rsplit('/', 1)[-1] else name + ':latest'


def missing_models(tags, env):
    if not isinstance(tags, dict) or not isinstance(tags.get('models'), list):
        raise StartupError('Ollama returned an invalid model list. Check OLLAMA_BASE_URL.')
    installed = {canonical_model(item.get('name', item.get('model', ''))) for item in tags.get('models', [])}
    requested = [env.get('OLLAMA_EMBED_MODEL', 'embeddinggemma'), env.get('OLLAMA_CHAT_MODEL', 'llama3.2:3b')]
    return [name for name in requested if canonical_model(name) not in installed]


def node_supported(version):
    try:
        parts = tuple(int(part) for part in version.strip().lstrip('v').split('.'))
        return len(parts) == 3 and parts >= (22, 12, 0)
    except ValueError:
        return False


def port_available(port):
    with socket.socket() as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def get_json(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def wait_ready(process, action, label, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise StartupError(f'{label} exited early. See logs/startup-{label.lower()}.log.')
        try:
            result = action()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(.5)
    raise StartupError(f'{label} did not become ready. See logs/startup-{label.lower()}.log.')


def checked_run(args, cwd, env):
    result = subprocess.run(args, cwd=cwd, env=env)
    if result.returncode:
        raise StartupError('Dependency installation failed. Fix the error above and relaunch.')


def frontend_dependencies_current(frontend=ROOT/'frontend'):
    """Detect stale node_modules after a pull, including transitive security updates."""
    try:
        manifest = json.loads((frontend/'package.json').read_text(encoding='utf-8'))
        expected = json.loads((frontend/'package-lock.json').read_text(encoding='utf-8'))['packages']
        installed = json.loads((frontend/'node_modules/.package-lock.json').read_text(encoding='utf-8'))['packages']
        for field in ('dependencies', 'devDependencies'):
            if manifest.get(field, {}) != expected[''].get(field, {}):
                return False
        for name, package in expected.items():
            if not name.startswith('node_modules/') or 'version' not in package:
                continue
            actual = installed.get(name)
            if actual is None and package.get('optional'):
                continue  # npm omits optional binaries for other operating systems.
            if not actual or actual.get('version') != package['version']:
                return False
        return (frontend/'node_modules/vite/bin/vite.js').exists()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def ensure_dependencies(env, install=False):
    if sys.version_info < (3, 10):
        raise StartupError('Python 3.10+ is required.')
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise StartupError('Install Node.js 22.12+ with npm and add it to PATH.')
    version = subprocess.check_output([node, '--version'], text=True).strip()
    if not node_supported(version):
        raise StartupError(f'Node.js 22.12+ is required by this frontend (found {version}).')
    packages = ('fastapi', 'uvicorn', 'pydantic', 'numpy', 'chromadb', 'sqlalchemy', 'psycopg')
    missing = [name for name in packages if importlib.util.find_spec(name) is None]
    if install or missing:
        print('Installing Python dependencies into the active Python interpreter...', flush=True)
        checked_run([sys.executable, '-m', 'pip', 'install', '-r', 'backend/requirements.txt',
                     '-r', 'ml/requirements.txt'], ROOT, env)
    vite = ROOT / 'frontend/node_modules/vite/bin/vite.js'
    if install or not frontend_dependencies_current():
        print('Installing locked frontend dependencies...', flush=True)
        checked_run([npm, 'ci'], ROOT / 'frontend', env)
    return node, vite


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Reinstall Python and locked npm dependencies')
    parser.add_argument('--check', action='store_true', help='Check prerequisites/models without starting services')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--smoke-test', action='store_true', help='Start, verify, and stop the services without opening a browser')
    options = parser.parse_args(argv)
    env = environment()
    processes, logs = [], []
    def launch(args, name, cwd=ROOT):
        log_dir = ROOT / 'logs'
        log_dir.mkdir(exist_ok=True)
        log = (log_dir / f'startup-{name.lower()}.log').open('w', encoding='utf-8')
        logs.append(log)
        process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        processes.append(process)
        return process
    try:
        if options.check:
            # Read-only check must not install packages or start a model server.
            if sys.version_info < (3, 10):
                raise StartupError('Python 3.10+ is required.')
            node = shutil.which('node')
            if not node or not node_supported(subprocess.check_output([node, '--version'], text=True)):
                raise StartupError('Node.js 22.12+ is required.')
            missing = [name for name in ('fastapi', 'uvicorn', 'pydantic', 'numpy', 'chromadb', 'sqlalchemy', 'psycopg')
                       if importlib.util.find_spec(name) is None]
            if missing or not frontend_dependencies_current():
                raise StartupError('Dependencies are missing. Run start_all.bat to install them.')
        else:
            node, vite = ensure_dependencies(env, options.install)
        for port in (8000, 8080):
            if not port_available(port):
                raise StartupError(f'Port {port} is already in use. Stop the existing service before relaunching.')
        base = env.get('OLLAMA_BASE_URL', 'http://127.0.0.1:11434').rstrip('/')
        try:
            tags = get_json(base + '/api/tags')
        except (OSError, ValueError):
            parsed = urlsplit(base)
            ollama = shutil.which('ollama')
            if options.check or not ollama or parsed.hostname not in ('127.0.0.1', 'localhost') or parsed.port not in (None, 11434):
                raise StartupError('Ollama is unreachable. Start Ollama or correct OLLAMA_BASE_URL.')
            print('Starting local Ollama...', flush=True)
            tags = wait_ready(launch([ollama, 'serve'], 'Ollama'), lambda: get_json(base + '/api/tags'), 'Ollama', 30)
        missing = missing_models(tags, env)
        if missing:
            commands = '\n'.join(f'  ollama pull {name}' for name in missing)
            raise StartupError('Required models are not installed. Run:\n' + commands)
        if options.check:
            print('Prerequisites, ports and exact model tags are ready.')
            return 0
        # Explicit local URL prevents a stale frontend environment from targeting another backend.
        env['VITE_API_BASE_URL'] = 'http://127.0.0.1:8000/api'
        origins = set(env.get('CORS_ORIGINS', '').split(',')) - {''}
        origins.update(('http://localhost:8080', 'http://127.0.0.1:8080'))
        env['CORS_ORIGINS'] = ','.join(sorted(origins))
        print('Starting backend and checking model readiness...', flush=True)
        health = wait_ready(launch([sys.executable, '-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000'], 'Backend'),
                            lambda: get_json('http://127.0.0.1:8000/api/health'), 'Backend')
        if health.get('status') != 'ready':
            raise StartupError('Backend started, but AI setup is incomplete. See logs/startup-backend.log and /api/health.')
        print('Starting frontend on its fixed demo port...', flush=True)
        def frontend_ready():
            with urllib.request.urlopen('http://127.0.0.1:8080', timeout=5) as response:
                return response.status == 200
        wait_ready(launch([node, str(vite), '--host', '127.0.0.1', '--port', '8080', '--strictPort'], 'Frontend', ROOT/'frontend'),
                   frontend_ready, 'Frontend')
        print('\nChaiGaram is ready: http://127.0.0.1:8080\nAPI docs: http://127.0.0.1:8000/docs\nLogs: logs/startup-*.log\n'
              'Keep this window open. Press Ctrl+C to stop the services launched here.', flush=True)
        if options.smoke_test:
            return 0
        if not options.no_browser:
            webbrowser.open('http://127.0.0.1:8080')
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise StartupError('A service stopped. See logs/startup-*.log and relaunch.')
            time.sleep(1)
    except KeyboardInterrupt:
        print('\nStopping ChaiGaram...', flush=True)
        return 0
    except (StartupError, OSError, subprocess.SubprocessError) as exc:
        print(f'\n[ERROR] {exc}', file=sys.stderr, flush=True)
        return 1
    finally:
        # Only stop processes this launcher created; never kill a pre-existing Ollama/service.
        for process in reversed(processes):
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
        for log in logs:
            log.close()


if __name__ == '__main__':
    raise SystemExit(main())
