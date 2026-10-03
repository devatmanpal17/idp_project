"""Smoke-test the real Linux deployment image using disposable Docker storage.

Does not pull AI models; /api/health correctly reports setup_required. Real model
and patent tests are separate. Requires a running Docker daemon and a built image.
"""
import argparse
import base64
import json
import os
import re
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from io import BytesIO
from zipfile import ZipFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', default='chaigaram-render:test')
    args = parser.parse_args()
    name = 'chaigaram-check-' + secrets.token_hex(5)
    volume = name+'-data'
    password = secrets.token_urlsafe(32)
    auth = 'Basic ' + base64.b64encode(('demo:'+password).encode()).decode()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {**os.environ, 'CHAI_HOST_PASSWORD': password}
    base = f'http://127.0.0.1:{port}'

    def docker(*command, **kwargs):
        return subprocess.run(['docker', *command], check=True, text=True,
                              env=env, capture_output=True, **kwargs).stdout.strip()

    def request(path, authenticated=False, method='GET', data=None):
        headers = {'Authorization': auth} if authenticated else {}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(base+path, headers=headers, method=method,
                                     data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            return response.status, response.headers, raw if path.endswith('.zip') else raw.decode()

    def ready():
        deadline = time.monotonic()+150
        while time.monotonic() < deadline:
            try:
                if request('/healthz')[0] == 200:
                    return
            except OSError:
                pass
            if docker('inspect', '-f', '{{.State.Running}}', name) != 'true':
                raise RuntimeError('Deployment container stopped during startup.')
            time.sleep(.5)
        raise RuntimeError('Deployment container did not become healthy.')

    try:
        docker('volume', 'create', volume)
        docker('run', '-d', '--name', name, '-p', f'127.0.0.1:{port}:10000',
               '--mount', f'type=volume,source={volume},target=/var/data',
               '-e', 'CHAI_HOST_PASSWORD', '-e', 'CHAI_MODEL_AUTO_PULL=false', args.image)
        ready()
        assert json.loads(request('/healthz')[2]) == {'status': 'ok'}
        for path in ('/', '/courses', '/api/health', '/api/learning/data', '/docs', '/openapi.json', '/downloads/chaigaram-extension.zip'):
            assert request(path)[0] == 401, path
        assert request('/api/rag/ingest', method='POST', data={})[0] == 401
        code, _, archive = request('/downloads/chaigaram-extension.zip', True)
        assert code == 200
        with ZipFile(BytesIO(archive)) as bundle:
            assert 'extension/manifest.json' in bundle.namelist()
            assert 'extension/background.js' in bundle.namelist()
            assert not any('.env' in item for item in bundle.namelist())
        code, headers, html = request('/', True)
        assert code == 200 and 'text/html' in headers['Content-Type'] and 'ChaiGaram' in html
        assert 'no-store' in headers['Cache-Control']
        assets = re.findall(r'(?:src|href)="([^" ]+\.(?:js|css))"', html)
        assert assets, 'SSR must include client assets'
        for asset in assets:
            if asset.startswith('/'):
                assert request(asset, True)[0] == 200, asset
                assert request(asset)[0] == 401, asset
        for path in ('/courses', '/mastery', '/quizzes', '/mistakes', '/study-plan',
                     '/recommendations', '/history', '/simulator', '/profile', '/settings'):
            code, headers, body = request(path, True)
            assert code == 200 and 'text/html' in headers['Content-Type'], path
            assert "This page didn't load" not in body, path
        health = json.loads(request('/api/health', True)[2])
        assert health['status'] == 'setup_required'
        assert health['analytics_database'] == 'sqlite'
        code, headers, _ = request('/api/learning/data', True)
        assert code == 200 and 'no-store' in headers['Cache-Control']
        assert request('/api/rag/ingest', True, 'POST', {})[0] == 422
        assert request('/api/tags', True)[0] == 404, 'Ollama endpoints must remain private'
        assert len(docker('port', name).splitlines()) == 1
        marker = 'deployment-persistence-check'
        script = ("import sqlite3; from pathlib import Path; "
                  "c=sqlite3.connect('/var/data/analytics.sqlite3'); "
                  "c.execute('CREATE TABLE deployment_check(value TEXT)'); "
                  f"c.execute('INSERT INTO deployment_check VALUES (?)',('{marker}',)); c.commit(); "
                  "Path('/var/data/chroma/check.txt').write_text('persist'); "
                  "Path('/var/data/ollama').mkdir(exist_ok=True); "
                  "Path('/var/data/ollama/check.txt').write_text('persist')")
        docker('exec', name, 'python', '-c', script)
        docker('restart', '-t', '110', name)
        ready()
        script = ("import sqlite3; from pathlib import Path; "
                  f"assert sqlite3.connect('/var/data/analytics.sqlite3').execute('SELECT value FROM deployment_check').fetchone()[0]=='{marker}'; "
                  "assert Path('/var/data/chroma/check.txt').read_text()=='persist'; "
                  "assert Path('/var/data/ollama/check.txt').read_text()=='persist'")
        docker('exec', name, 'python', '-c', script)
        assert request('/api/learning/data', True)[0] == 200
        docker('stop', '-t', '110', name)
        assert docker('inspect', '-f', '{{.State.ExitCode}}', name) == '0'
        print('PASS: password boundary, SSR routes/assets, API validation, private Ollama, persistence and graceful shutdown.')
    except Exception:
        logs = subprocess.run(['docker', 'logs', name], text=True, capture_output=True)
        # Use a disposable password but redact defensively if an upstream tool logs it.
        print((logs.stdout+logs.stderr).replace(password, '[redacted]'))
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
