"""Isolated Chrome/CDP acceptance run against real local backend and Ollama.

Requires Chrome, websocket-client, imageio-ffmpeg, installed frontend dependencies, and Ollama.
Uses temporary databases and a fresh browser profile; never touches a user profile.
"""
import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
from io import BytesIO
from pathlib import Path

import websocket
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.getenv('CHAI_BROWSER_CHECK_OUTPUT', str(ROOT / 'patent/results')))
LESSON = ('Binary search works on a sorted sequence and repeatedly cuts the search interval in half. '
          'It compares the middle value with the target value. If the target is smaller, the search '
          'continues in the left half. If the target is larger, it continues in the right half. '
          'The process ends when the target is found or the interval is empty. '
          'Before searching, values must be sorted in ascending order; otherwise a midpoint comparison '
          'cannot identify which half may contain the target. Each comparison removes roughly half the '
          'remaining candidates, so the number of comparisons grows logarithmically with collection size. '
          'A sorted collection of 1024 values needs at most about ten halving steps to isolate one position. '
          'If the target is absent, the lower bound eventually passes the upper bound. A sequential scan '
          'does not need sorted input, but may inspect every value before finding a match or proving absence.')


def http(url, data=None):
    request = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def until(action, timeout=90):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            result = action()
            if result:
                return result
        except Exception as exc:
            error = exc
        time.sleep(.25)
    raise TimeoutError(f'Condition did not become true: {error}')


def contact_sheet(items, destination, columns, thumb_width, thumb_height):
    if not items:
        return
    rows = (len(items) + columns - 1) // columns
    tile_height = thumb_height + 28
    canvas = Image.new('RGB', (columns * thumb_width, rows * tile_height), '#141414')
    draw = ImageDraw.Draw(canvas)
    for index, (label, raw) in enumerate(items):
        image = Image.open(BytesIO(raw)).convert('RGB')
        image = ImageOps.contain(image, (thumb_width, thumb_height))
        x, y = (index % columns) * thumb_width, (index // columns) * tile_height
        canvas.paste(image, (x, y + 28))
        draw.text((x + 6, y + 7), label, fill='#ffffff')
    canvas.save(destination)


class CDP:
    def __init__(self, url):
        self.socket = websocket.create_connection(url, timeout=190, suppress_origin=True)
        self.sequence = 0
        self.events = []

    def call(self, method, params=None, session=None):
        self.sequence += 1
        payload = {'id': self.sequence, 'method': method, 'params': params or {}}
        if session:
            payload['sessionId'] = session
        self.socket.send(json.dumps(payload))
        while True:
            message = json.loads(self.socket.recv())
            if message.get('id') == self.sequence:
                if 'error' in message:
                    raise RuntimeError(f'{method}: {message["error"]}')
                return message.get('result', {})
            self.events.append(message)

    def page(self, url):
        target = self.call('Target.createTarget', {'url': 'about:blank'})['targetId']
        session = self.call('Target.attachToTarget', {'targetId': target, 'flatten': True})['sessionId']
        for domain in ('Page', 'Runtime', 'Network', 'Log'):
            self.call(domain + '.enable', session=session)
        self.call('Target.activateTarget', {'targetId': target})
        self.call('Page.navigate', {'url': url}, session)
        return session

    def evaluate(self, expression, session):
        response = self.call('Runtime.evaluate', {'expression': expression, 'returnByValue': True,
                                                  'awaitPromise': True}, session)
        if response.get('exceptionDetails'):
            raise RuntimeError(str(response['exceptionDetails']))
        return response.get('result', {}).get('value')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'runtime_errors': [], 'api_errors': []}
    processes, logs = [], []
    ui_images = {'desktop': [], 'mobile': []}
    cdp = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        env = os.environ.copy()
        env.update(DATABASE_URL=f'sqlite:///{(temp / "analytics.db").as_posix()}',
                   CHROMA_PERSIST_DIR=str(temp / 'chroma'),
                   CORS_ORIGINS='http://127.0.0.1:8081,http://localhost:8081',
                   VITE_API_BASE_URL='http://127.0.0.1:8001/api')
        def launch(args, name, cwd=ROOT):
            log = (OUTPUT / (name + '.log')).open('w', encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            return process
        def record(name, details=None):
            report['checks'].append({'name': name, 'passed': True, 'details': details})
            print(name + ': passed', flush=True)
        def click(text, session):
            return cdp.evaluate(f"(() => {{ const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim().includes({json.dumps(text)})); if (!b || b.disabled) return false; b.click(); return true; }})()", session)
        def capture_ui(label, viewport, session):
            raw = base64.b64decode(cdp.call('Page.captureScreenshot', {'format': 'png'}, session)['data'])
            ui_images[viewport].append((label, raw))
            layout = cdp.evaluate("({width:window.innerWidth,scrollWidth:document.documentElement.scrollWidth,brokenImages:[...document.images].filter(image=>!image.complete || image.naturalWidth===0).length})", session)
            report.setdefault('ui_checks', []).append({'route': label, 'viewport': viewport, **layout})
        try:
            launch([sys.executable, '-m', 'uvicorn', 'backend.app:app', '--port', '8001'], 'browser-backend')
            launch([shutil.which('node'), str(ROOT / 'frontend/node_modules/vite/bin/vite.js'),
                    '--host', '127.0.0.1', '--port', '8081', '--strictPort'], 'browser-frontend', ROOT / 'frontend')
            until(lambda: http('http://127.0.0.1:8001/api/health'))
            until(lambda: urllib.request.urlopen('http://127.0.0.1:8081', timeout=5).status == 200)
            chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
            profile = temp / 'browser'
            launch([str(chrome), '--headless=new', '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', '--enable-unsafe-extension-debugging',
                    '--remote-debugging-port=0', f'--user-data-dir={profile}', '--window-size=1440,1000'], 'browser-chrome')
            port = until(lambda: (profile / 'DevToolsActivePort').read_text().splitlines()[0])
            cdp = CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])
            # Real MV3 loading, not an injected imitation of extension APIs.
            extension_id = cdp.call('Extensions.loadUnpacked', {'path': str(ROOT / 'extension')})['id']
            setup = cdp.page(f'chrome-extension://{extension_id}/options.html')
            until(lambda: cdp.evaluate("Boolean(globalThis.chrome?.storage?.sync)", setup))
            record('unpacked_extension_loaded', extension_id)
            session = cdp.page('http://127.0.0.1:8081/quizzes')
            until(lambda: cdp.evaluate("Boolean(document.querySelector('textarea'))", session))
            until(lambda: cdp.evaluate("Object.keys(document.querySelector('textarea')).some(key => key.startsWith('__reactFiber'))", session))
            # Use the dashboard's real ingestion form.
            for selector, value in [("input[placeholder='Source title (for citations)']", 'Browser test lesson'),
                                    ("input[placeholder='Topic']", 'Binary search'), ('textarea', LESSON)]:
                cdp.evaluate(f"document.querySelector({json.dumps(selector)}).focus()", session)
                cdp.call('Input.insertText', {'text': value}, session)
            until(lambda: click('Index in ChromaDB', session))
            until(lambda: cdp.evaluate("document.body.innerText.includes('Indexed 1 semantic chunks')", session), 180)
            record('dashboard_document_ingestion')
            skip_quiz = os.environ.get('BROWSER_SKIP_LIVE_QUIZ') == '1'
            report['live_quiz_skipped'] = skip_quiz
            if not skip_quiz:
                until(lambda: click('Generate New AI Practice Quiz', session))
                until(lambda: cdp.evaluate("[...document.querySelectorAll('button')].filter(b => /^A\\./.test(b.innerText.trim())).length === 3", session), 300)
                # Read only the disposable test database to select one wrong
                # choice and two correct choices deterministically, independent
                # of the model's randomized answer positions.
                connection = sqlite3.connect(temp / 'analytics.db')
                try:
                    stored = connection.execute('SELECT questions_json FROM generated_quizzes ORDER BY created_at DESC LIMIT 1').fetchone()
                finally:
                    connection.close()
                questions = json.loads(stored[0])
                selected = [next(choice for choice in q['choices'] if choice != q['answer']) if index == 0
                            else q['answer'] for index, q in enumerate(questions)]
                cdp.evaluate(f"(() => {{ const choices=[...document.querySelectorAll('button')].filter(b=>/^[A-D]\\./.test(b.innerText.trim())); {json.dumps(selected)}.forEach((value,index)=>{{ const button=choices.slice(index*4,index*4+4).find(b=>b.querySelector('span.flex-1')?.textContent === value); if (!button) throw new Error('Quiz choice was not found'); button.click(); }}); }})()", session)
                until(lambda: click('Submit for Diagnostic Evaluation', session))
                until(lambda: cdp.evaluate("document.body.innerText.includes('Assessment Mastery: Before and After')", session))
                record('dashboard_quiz_generation_and_scoring')
                notebook = http('http://127.0.0.1:8001/api/learning/mistakes')
                assert notebook['summary']['due'] == 1, notebook
                card = notebook['items'][0]
                cdp.call('Page.navigate', {'url': 'http://127.0.0.1:8081/mistakes'}, session)
                until(lambda: cdp.evaluate("document.querySelectorAll('[data-review-card]').length === 1", session))
                assert not cdp.evaluate("document.body.innerText.includes('Expected answer:')", session)
                until(lambda: click('Reveal feedback', session))
                until(lambda: cdp.evaluate("document.body.innerText.includes('Expected answer:')", session))
                capture_ui('/mistakes/revealed', 'desktop', session)
                record('mistake_notebook_recall_and_reveal')
                until(lambda: click('Again', session))
                until(lambda: cdp.evaluate("document.body.innerText.includes('Review saved.')", session))
                scheduled = http('http://127.0.0.1:8001/api/learning/mistakes?include_scheduled=true')['items'][0]
                assert scheduled['version'] == 1 and scheduled['streak'] == 0
                assert scheduled['due_at'] > notebook['server_time']
                cdp.call('Page.reload', {}, session)
                until(lambda: cdp.evaluate("document.body.innerText.includes(\"You're up to date\")", session))
                until(lambda: click('All cards', session))
                until(lambda: cdp.evaluate("document.querySelectorAll('[data-review-card]').length === 1", session))
                assert not cdp.evaluate("document.body.innerText.includes('Expected answer:')", session)
                record('mistake_notebook_again_persists_after_reload')
                until(lambda: click('Reveal feedback', session))
                until(lambda: click('Remembered', session))
                until(lambda: cdp.evaluate("document.body.innerText.includes('Review saved.')", session))
                scheduled = http('http://127.0.0.1:8001/api/learning/mistakes?include_scheduled=true')['items'][0]
                assert scheduled['id'] == card['id'] and scheduled['version'] == 2
                assert scheduled['streak'] == 1 and scheduled['review_count'] == 2
                assert not http('http://127.0.0.1:8001/api/learning/mistakes')['items']
                record('mistake_notebook_remembered_schedule')
            data = http('http://127.0.0.1:8001/api/learning/data')
            course = data['courses'][0]['id']
            for path in ['/', '/courses', '/courses/' + course, '/mastery', '/quizzes', '/mistakes', '/study-plan', '/recommendations', '/history', '/simulator', '/profile', '/settings']:
                cdp.call('Page.navigate', {'url': 'http://127.0.0.1:8081' + path}, session)
                until(lambda: cdp.evaluate("document.readyState === 'complete' && Boolean(document.querySelector('h1'))", session))
                time.sleep(.6)
                heading = cdp.evaluate("document.querySelector('h1').innerText", session)
                assert not any(value in heading for value in ['404', "didn’t load", "didn't load"]), heading
                record('screen:' + path, heading)
                capture_ui(path, 'desktop', session)
            until(lambda: cdp.evaluate("document.body.innerText.includes('Capture and recovery')", session))
            until(lambda: click('Save', session))
            until(lambda: cdp.evaluate("document.body.innerText.includes('Local model configuration updated.')", session))
            record('settings_save_and_diagnostics')
            screenshot = cdp.call('Page.captureScreenshot', {'format': 'png'}, session)['data']
            (OUTPUT / 'settings.png').write_bytes(base64.b64decode(screenshot))
            cdp.call('Emulation.setDeviceMetricsOverride', {
                'width': 390, 'height': 844, 'deviceScaleFactor': 1, 'mobile': True}, session)
            for path in ['/', '/courses', '/courses/' + course, '/mastery', '/quizzes', '/mistakes', '/study-plan',
                         '/recommendations', '/history', '/simulator', '/profile', '/settings']:
                cdp.call('Page.navigate', {'url': 'http://127.0.0.1:8081' + path}, session)
                until(lambda: cdp.evaluate("document.readyState === 'complete' && Boolean(document.querySelector('h1'))", session))
                time.sleep(.7)
                capture_ui(path, 'mobile', session)
            cdp.evaluate("document.querySelector('button[title=\"Change theme\"]').click()", session)
            until(lambda: cdp.evaluate("document.documentElement.classList.contains('light')", session))
            light = cdp.call('Page.captureScreenshot', {'format': 'png'}, session)['data']
            (OUTPUT / 'ui_light_mobile.png').write_bytes(base64.b64decode(light))
            cdp.evaluate("document.querySelector('button[title=\"Change theme\"]').click()", session)
            until(lambda: cdp.evaluate("!document.documentElement.classList.contains('light')", session))
            record('mobile_theme_toggle')
            cdp.evaluate("document.querySelector('button[aria-label=\"Toggle navigation\"]').click()", session)
            until(lambda: cdp.evaluate("Boolean(document.querySelector('nav[aria-label=\"Mobile navigation\"]'))", session))
            cdp.evaluate("document.querySelector('nav[aria-label=\"Mobile navigation\"] a[href=\"/courses\"]').click()", session)
            until(lambda: cdp.evaluate("location.pathname === '/courses' && document.querySelector('h1')?.innerText === 'Courses'", session))
            record('mobile_navigation')
            cdp.call('Emulation.clearDeviceMetricsOverride', session=session)
            if not skip_quiz:
                cdp.call('Browser.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': str(temp / 'downloads')})
                cdp.call('Page.navigate', {'url': 'http://127.0.0.1:8081/study-plan'}, session)
                until(lambda: click('Download .ics', session))
                calendar = until(lambda: next((temp / 'downloads').glob('*.ics'), None))
                assert 'BEGIN:VEVENT' in calendar.read_text()
                record('study_calendar_export')
            # Load extension options and verify the real background connection.
            options = cdp.page(f'chrome-extension://{extension_id}/options.html')
            until(lambda: cdp.evaluate("document.readyState === 'complete' && Boolean(document.getElementById('apiBaseUrl')?.value)", options))
            cdp.evaluate("document.getElementById('apiBaseUrl').value='http://127.0.0.1:8001'; document.getElementById('dashboardUrl').value='http://127.0.0.1:8081'", options)
            cdp.evaluate("document.getElementById('save').click()", options)
            until(lambda: cdp.evaluate("document.getElementById('result').textContent.includes('online')", options))
            record('extension_options_and_background_health')
            # A static article in an isolated local server exercises actual content capture.
            (temp / 'article.html').write_text(f'<html><head><title>Binary search lesson</title></head><body><main><h1>Binary search</h1><p>{LESSON}</p></main></body></html>', encoding='utf-8')
            launch([sys.executable, '-m', 'http.server', '8091', '--bind', '127.0.0.1', '--directory', str(temp)], 'browser-article')
            until(lambda: urllib.request.urlopen('http://127.0.0.1:8091/article.html', timeout=5).status == 200)
            article = cdp.page('http://127.0.0.1:8091/article.html')
            shadow = "document.getElementById('chaigaram-extension-root')?.shadowRoot"
            until(lambda: cdp.evaluate(f'Boolean({shadow})', article))
            cdp.evaluate("chrome.tabs.query({url:'http://127.0.0.1:8091/article.html'}).then(([tab]) => chrome.tabs.sendMessage(tab.id,{type:'CHAIGARAM_TOGGLE'}))", options)
            cdp.evaluate(f"{shadow}.getElementById('summarize').click()", article)
            until(lambda: cdp.evaluate(f"({shadow}.getElementById('answer').innerText || '').length > 80", article), 240)
            record('extension_article_summary')
            cdp.evaluate("const root = document.getElementById('chaigaram-extension-root').shadowRoot; root.getElementById('question').value='How does binary search reduce the interval?'; root.getElementById('ask').click()", article)
            until(lambda: cdp.evaluate(f"!{shadow}.getElementById('ask').disabled && ({shadow}.getElementById('answer').innerText || '').length > 40", article), 240)
            record('extension_article_question')
            # Generate a deterministic local clip with real decoded frames.
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=10:duration=12',
                            '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '40', '-an', '-y',
                            str(temp / 'fixture.webm')], check=True, capture_output=True)
            (temp / 'video.html').write_text('''<html><head><title>Observation test</title></head>
<body><h1>Observation test video</h1><video muted controls width="640" height="360" preload="auto"></video>
<script>
async function prepareVideo() {
 const video=document.querySelector('video');
 video.src=URL.createObjectURL(await fetch('fixture.webm').then(response=>response.blob()));
 const track=video.addTextTrack('captions','English','en');track.mode='showing';
 track.addCue(new VTTCue(.5,1.5,'Observed opening phrase about sorted sequences.'));
 track.addCue(new VTTCue(4,5,'Skipped secret is a copper lantern.'));
 track.addCue(new VTTCue(8.5,9.5,'Observed ending phrase about binary search.'));
 await new Promise((resolve,reject)=>{
   if(video.readyState>=2) return resolve();
   video.addEventListener('loadeddata',resolve,{once:true});
   video.addEventListener('error',()=>reject(new Error(video.error?.message)),{once:true});
   video.load();
 });
 return true;
}
</script></body></html>''', encoding='utf-8')
            video_page = cdp.page('http://127.0.0.1:8091/video.html')
            until(lambda: cdp.evaluate('typeof prepareVideo === "function"', video_page))
            until(lambda: cdp.evaluate("document.visibilityState === 'visible'", video_page))
            cdp.evaluate('prepareVideo()', video_page)
            time.sleep(1)
            cdp.evaluate("""(() => { const video = document.querySelector('video');
                const seek = () => { if (video.currentTime >= 2) {
                    video.removeEventListener('timeupdate', seek);
                    video.pause(); window.seekFrom = video.currentTime;
                    video.addEventListener('seeked', () => {
                        window.seekTo = video.currentTime;
                        if (window.seekTo >= 7.5) video.play();
                    }, {once:true});
                    video.currentTime = 8;
                }};
                video.addEventListener('timeupdate', seek); video.play();
            })()""", video_page)
            until(lambda: cdp.evaluate('Number.isFinite(window.seekFrom)', video_page))
            assert cdp.evaluate('window.seekFrom < 3', video_page), 'Video seek started after the intended gap.'
            until(lambda: cdp.evaluate('window.seekTo >= 7.5', video_page))
            until(lambda: cdp.evaluate('document.querySelector("video").currentTime > 10', video_page))
            cdp.evaluate('document.querySelector("video").pause()', video_page)
            def observed_video():
                docs = http('http://127.0.0.1:8001/api/vectors/diagnostics')['documents']
                return next((doc for doc in docs if doc['counts'].get('ACTIVE', 0) >= 2), None)
            observed = until(observed_video, 180)
            report['video_observation_before_speculation'] = observed
            assert not any(start <= 4000 and end >= 5000 for start, end in observed['observed_intervals']), observed
            visible = http('http://127.0.0.1:8001/api/rag/retrieve', {'query': 'secret copper lantern', 'document_id': observed['document_id']})
            report['video_retrieved_chunks'] = visible['chunks']
            assert 'copper lantern' not in json.dumps(visible['chunks'])
            # Idle speculation may run later than playback. Request it explicitly
            # so this check also verifies the SEALED state outside the ANN index.
            for _ in range(5):
                observed = next(doc for doc in http('http://127.0.0.1:8001/api/vectors/diagnostics')['documents']
                                if doc['document_id'] == observed['document_id'])
                if observed['counts'].get('SEALED', 0) == 1:
                    break
                job = http('http://127.0.0.1:8001/api/vectors/speculate', {
                    'document_id': observed['document_id'], 'position_ms': 2000,
                    'budget_ms': 10000, 'idle': True, 'observed_only': False})
                if job.get('job_id'):
                    until(lambda: http(f"http://127.0.0.1:8001/api/jobs/{job['job_id']}")['status'] in ('succeeded', 'failed'), 60)
                time.sleep(1)
            observed = next(doc for doc in http('http://127.0.0.1:8001/api/vectors/diagnostics')['documents']
                            if doc['document_id'] == observed['document_id'])
            assert observed['counts'].get('SEALED', 0) == 1, observed
            record('extension_real_video_seek_gap_stays_sealed', observed)
            cdp.call('Page.navigate', {'url': 'http://127.0.0.1:8081/history'}, session)
            until(lambda: cdp.evaluate("[...document.querySelectorAll('button')].some(button=>button.innerText.trim()==='Delete')", session))
            cdp.evaluate("window.confirm=()=>true; [...document.querySelectorAll('button')].find(button=>button.innerText.trim()==='Delete').click()", session)
            until(lambda: cdp.evaluate("document.body.innerText.includes('This source will no longer be used for quizzes.')", session))
            record('history_delete_from_ui')
            for event in cdp.events:
                method, params = event.get('method'), event.get('params', {})
                if method == 'Runtime.exceptionThrown':
                    report['runtime_errors'].append(params.get('exceptionDetails'))
                if method == 'Network.responseReceived':
                    response = params.get('response', {})
                    if '/api/' in response.get('url', '') and response.get('status', 0) >= 400:
                        report['api_errors'].append({'url': response['url'], 'status': response['status']})
            assert not report['runtime_errors'], report['runtime_errors']
            assert not report['api_errors'], report['api_errors']
        except Exception as exc:
            report['failure'] = str(exc)
            if cdp:
                try:
                    report['last_page_text'] = cdp.evaluate('document.body.innerText', session)[-6000:]
                except Exception:
                    pass
            raise
        finally:
            (OUTPUT / 'browser_checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            contact_sheet(ui_images['desktop'], OUTPUT / 'ui_desktop.png', 2, 600, 380)
            contact_sheet(ui_images['mobile'], OUTPUT / 'ui_mobile.png', 5, 240, 430)
            if cdp:
                try:
                    cdp.call('Browser.close')
                except Exception:
                    pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
            for log in logs:
                log.close()


if __name__ == '__main__':
    main()
