"""Smoke-test the real Linux deployment image using disposable Docker storage.

Tests safe first-boot provisioning, then downloads the real models and checks CPU
inference, patent behaviors and restart persistence. Uses disposable storage only.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
import traceback
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

    def request(path, authenticated=False, method='GET', data=None, timeout=15):
        headers = {'Authorization': auth} if authenticated else {}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(base+path, headers=headers, method=method,
                                     data=json.dumps(data).encode() if data is not None else None)
        try:
            response = urllib.request.urlopen(req, timeout=timeout)
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

    def ai_ready():
        deadline = time.monotonic()+900
        probe_failures = 0
        while time.monotonic() < deadline:
            try:
                if json.loads(request('/api/health', True)[2]).get('status') == 'ready':
                    return
            except (OSError, ValueError):
                pass
            assert docker('inspect', '-f', '{{.State.Running}}', name) == 'true'
            try:
                available = request('/healthz', timeout=5)[0] == 200
            except OSError:
                available = False
            # Replacing setup with FastAPI can briefly close its loopback socket.
            probe_failures = 0 if available else probe_failures + 1
            assert probe_failures < 5, 'Probes must stay available during model installation'
            time.sleep(2)
        raise RuntimeError('AI models did not finish installing in 15 minutes.')

    def start(*extra):
        docker('run', '-d', '--name', name, '--cpus', '4', '--memory', '8g',
               '-p', f'127.0.0.1:{port}:10000',
               '--mount', f'type=volume,source={volume},target=/var/data',
               '-e', 'CHAI_HOST_PASSWORD', '-e', 'DATABASE_URL=',
               '-e', 'RENDER_EXTERNAL_URL=https://deployment-check.onrender.com', *extra, args.image)
        ready()

    try:
        docker('volume', 'create', volume)
        start('-e', 'CHAI_MODEL_AUTO_PULL=false')
        assert json.loads(request('/healthz')[2]) == {'status': 'ok'}
        assert json.loads(request('/api/health', True)[2])['status'] == 'setup_required'
        code, headers, body = request('/api/rag/ingest', True, 'POST', {})
        assert code == 503 and headers['Retry-After'] == '30' and 'installed' in body
        assert request('/api/vectors/transcript', True, 'POST', {})[0] == 503
        docker('exec', name, 'python', '-c', "from pathlib import Path; assert not Path('/var/data/analytics.sqlite3').exists()")
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
        docker('stop', '-t', '110', name)
        assert docker('inspect', '-f', '{{.State.ExitCode}}', name) == '0'
        docker('rm', name)
        print('PASS: gated dashboard and fast probes during setup; patent writes blocked before model identity is resolved.', flush=True)
        start()  # Exercise the default automatic first-boot model download path.
        ai_ready()
        health = json.loads(request('/api/health', True)[2])
        assert health['status'] == 'ready'
        assert health['analytics_database'] == 'sqlite'
        code, headers, _ = request('/api/learning/data', True)
        assert code == 200 and 'no-store' in headers['Cache-Control']
        assert request('/api/rag/ingest', True, 'POST', {})[0] == 422
        assert request('/api/tags', True)[0] == 404, 'Ollama endpoints must remain private'
        assert len(docker('port', name).splitlines()) == 1
        topic = 'Hosted persistence'
        content = ('Binary search requires a sorted sequence. Each step compares the middle value '
                   'with the target, then keeps the left or right half of the search interval.')
        code, _, body = request('/api/rag/ingest', True, 'POST',
                              dict(title=topic, topic=topic, content=content), timeout=150)
        assert code == 200, body
        document_id = json.loads(body)['document_id']
        def retrieved():
            code, _, body = request('/api/rag/retrieve', True, 'POST',
                dict(topic=topic, query='What does binary search require?', top_k=2), timeout=150)
            assert code == 200, body
            result = json.loads(body)['chunks']
            assert result and result[0]['snippet'] == content, result
            return [chunk['chunk_id'] for chunk in result]
        chunk_ids = retrieved()
        code, _, body = request('/api/vectors/transcript', True, 'POST',
            dict(source_url='https://demo.test/lesson', topic=topic,
                 captions=[dict(start_ms=0, end_ms=1000, text=content)]))
        assert code == 200, body
        temporal_id = json.loads(body)['document_id']
        print('PASS: default automatic model install, CPU embedding, SQL and Chroma API writes.', flush=True)

        # Copy only the acceptance driver into the test container, never a host .env.
        docker('exec', name, 'mkdir', '-p', '/app/scripts')
        docker('cp', str(Path(__file__).with_name('check_patent_features.py')), name+':/app/scripts/check_patent_features.py')
        output = docker('exec', name, 'python', '/app/scripts/check_patent_features.py',
                        '--output', '/tmp/patent-check.json', timeout=900)
        print(output, flush=True)
        docker('exec', name, 'python', '-c', "import json; r=json.load(open('/tmp/patent-check.json')); assert r['success'] and len(r['checks'])==9")
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
        ai_ready()
        assert request('/api/learning/data', True)[0] == 200
        assert json.loads(request('/api/health', True)[2])['collection'] == health['collection']
        assert retrieved() == chunk_ids, 'Restart must preserve vector identities and content'
        diagnostics = json.loads(request('/api/vectors/diagnostics', True)[2])
        assert any(item['document_id'] == temporal_id for item in diagnostics['documents']), diagnostics
        assert document_id
        print('PASS: model identity and actual document/patent records survive a full restart.', flush=True)

        # An exited dependency must terminate the supervisor, allowing platform restart.
        for command in ('node', 'ollama', 'uvicorn'):
            script = ("import os,signal; from pathlib import Path; "
                      "entries=[(p, (p/'cmdline').read_bytes().split(b'\\0')) for p in Path('/proc').iterdir() if p.name.isdigit() and (p/'cmdline').exists()]; "
                      f"targets=[int(p.name) for p,a in entries if a and (a[0]==b'{command}' "
                      f"or (b'{command}' in a and b'backend.app:app' in a))]; "
                      "assert targets, 'Required process not found'; os.kill(targets[0],signal.SIGKILL)")
            docker('exec', name, 'python', '-c', script)
            deadline = time.monotonic()+110
            while docker('inspect', '-f', '{{.State.Running}}', name) == 'true':
                assert time.monotonic() < deadline, 'A dead required process must stop the container'
                time.sleep(.5)
            assert docker('inspect', '-f', '{{.State.ExitCode}}', name) != '0'
            docker('start', name)
            ready()
            ai_ready()
            assert retrieved() == chunk_ids
        print('PASS: Dashboard, Ollama and API failure detection, recovery and persisted retrieval.', flush=True)
        docker('stop', '-t', '110', name)
        assert docker('inspect', '-f', '{{.State.ExitCode}}', name) == '0'
        print('PASS: password boundary, SSR, first boot, real CPU models/patent checks, persistence, failure recovery and graceful shutdown.')
    except Exception as exc:
        logs = subprocess.run(['docker', 'logs', name], text=True, capture_output=True)
        # Use a disposable password but redact defensively if an upstream tool logs it.
        print((logs.stdout+logs.stderr).replace(password, '[redacted]'))
        detail = traceback.format_exc()
        if isinstance(exc, subprocess.CalledProcessError):
            detail += '\n' + (exc.stdout or '') + '\n' + (exc.stderr or '')
        detail = detail.replace(password, '[redacted]')
        print(detail, flush=True)
        if os.getenv('GITHUB_ACTIONS') == 'true':
            # Make the concrete failure available in the public check annotation,
            # including stderr from acceptance drivers run with docker exec.
            escaped = detail.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print('::error::' + escaped, flush=True)
        raise
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True)


if __name__ == '__main__':
    main()
