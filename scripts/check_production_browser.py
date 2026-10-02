"""Exercise the built Cloudflare worker through npm run preview and real Chrome.

Uses disposable SQLite/Chroma and a fresh browser profile. Requires a completed
frontend build, installed dependencies, Chrome, and the configured Ollama models.
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
from pathlib import Path

from check_browser import CDP, LESSON, ROOT, contact_sheet, http, until
from start_local import port_available

OUTPUT = Path(os.getenv('CHAI_PRODUCTION_CHECK_OUTPUT', str(ROOT/'benchmarks/results/demo-readiness-20261002/production')))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = dict(checks=[], layouts=[], runtime_errors=[], api_errors=[])
    processes, logs = [], []
    cdp = None
    images = dict(desktop=[], mobile=[])
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        env = os.environ.copy()
        env.update(DATABASE_URL=f'sqlite:///{(temp/"analytics.db").as_posix()}',
                   CHROMA_PERSIST_DIR=str(temp/'chroma'), WRANGLER_SEND_METRICS='false')
        def launch(args, name, cwd=ROOT):
            log = (OUTPUT/f'{name}.log').open('w',encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            processes.append(process)
            return process
        def record(name):
            report['checks'].append(dict(name=name,passed=True))
            print(name+': passed',flush=True)
        def text(session):
            return cdp.evaluate('document.body.innerText',session)
        def click(label, session):
            return cdp.evaluate(f"(() => {{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().includes({json.dumps(label)}));if(!b||b.disabled)return false;b.click();return true;}})()",session)
        def loaded(session):
            return cdp.evaluate("Boolean(document.querySelector('main h1')) && !document.body.innerText.includes(\"This page didn't load\") && !document.body.innerText.includes('Loading your learning space')",session)
        try:
            for port in (8000,8080):
                if not port_available(port):
                    raise RuntimeError(f'Production check requires free port {port}; no existing service will be stopped.')
            if not (ROOT/'frontend/dist/server/wrangler.json').exists():
                raise RuntimeError('Run npm run build from frontend first.')
            launch([sys.executable,'-m','uvicorn','backend.app:app','--port','8000'], 'backend')
            until(lambda:http('http://127.0.0.1:8000/api/health').get('status')=='ready')
            node=Path(shutil.which('node'))
            npm_cli=node.parent/'node_modules/npm/bin/npm-cli.js' if os.name=='nt' else Path(shutil.which('npm')).resolve()
            preview=launch([str(node),str(npm_cli),'run','preview'],'preview',ROOT/'frontend')
            def ready():
                if preview.poll() is not None:
                    raise RuntimeError('Production preview exited. See preview.log.')
                with urllib.request.urlopen('http://127.0.0.1:8080',timeout=5) as response:
                    return response.status==200
            until(ready,120)
            record('production_preview_starts_on_windows')
            http('http://127.0.0.1:8000/api/rag/ingest',dict(title='Production fixture',topic='Binary search',content=LESSON))
            profile=temp/'chrome'
            chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            launch([str(chrome),'--headless=new','--no-first-run','--disable-background-networking',
                    '--remote-debugging-port=0',f'--user-data-dir={profile}','--window-size=1440,1000'],'chrome')
            port=until(lambda:(profile/'DevToolsActivePort').read_text().splitlines()[0])
            cdp=CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])
            session=cdp.page('http://127.0.0.1:8080/quizzes')
            until(lambda:loaded(session))
            until(lambda:click('Generate New AI Practice Quiz',session))
            until(lambda:cdp.evaluate("[...document.querySelectorAll('button')].filter(b=>/^A\\./.test(b.innerText.trim())).length===3",session),300)
            with sqlite3.connect(temp/'analytics.db') as connection:
                questions=json.loads(connection.execute('SELECT questions_json FROM generated_quizzes ORDER BY created_at DESC LIMIT 1').fetchone()[0])
            answers=[next(choice for choice in q['choices'] if choice!=q['answer']) if i==0 else q['answer'] for i,q in enumerate(questions)]
            cdp.evaluate(f"(() => {{const choices=[...document.querySelectorAll('button')].filter(b=>/^[A-D]\\./.test(b.innerText.trim()));{json.dumps(answers)}.forEach((answer,i)=>choices.slice(i*4,i*4+4).find(b=>b.querySelector('span.flex-1')?.textContent===answer).click());}})()",session)
            until(lambda:click('Submit for Diagnostic Evaluation',session))
            until(lambda:'Assessment Mastery: Before and After' in text(session))
            record('production_quiz_generation_scoring_and_graphs')
            cdp.call('Page.navigate',{'url':'http://127.0.0.1:8080/mistakes'},session)
            until(lambda:cdp.evaluate("document.querySelectorAll('[data-review-card]').length===1",session))
            until(lambda:click('Reveal feedback',session))
            until(lambda:'Expected answer:' in text(session))
            until(lambda:click('Remembered',session))
            until(lambda:'Review saved.' in text(session))
            cdp.call('Page.reload',{},session)
            until(lambda:"You're up to date" in text(session))
            record('production_mistake_review_persists')
            data=http('http://127.0.0.1:8000/api/learning/data')
            routes=['/','/courses','/courses/'+data['courses'][0]['id'],'/mastery','/quizzes','/mistakes',
                    '/study-plan','/recommendations','/history','/simulator','/profile','/settings']
            for viewport,width,height in [('desktop',1440,1000),('mobile',390,844)]:
                cdp.call('Emulation.setDeviceMetricsOverride',dict(width=width,height=height,deviceScaleFactor=1,mobile=viewport=='mobile'),session)
                for route in routes:
                    with urllib.request.urlopen('http://127.0.0.1:8080'+route,timeout=15) as response:
                        assert response.status==200
                    cdp.call('Page.navigate',{'url':'http://127.0.0.1:8080'+route},session)
                    until(lambda:loaded(session))
                    until(lambda:'Engine offline' not in text(session))
                    time.sleep(.4)
                    layout=cdp.evaluate("({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,brokenImages:[...document.images].filter(i=>!i.complete||i.naturalWidth===0).length})",session)
                    assert layout['scrollWidth']<=layout['width'] and layout['brokenImages']==0,layout
                    report['layouts'].append(dict(route=route,viewport=viewport,**layout))
                    images[viewport].append((route,base64.b64decode(cdp.call('Page.captureScreenshot',{'format':'png'},session)['data'])))
                record('production_'+viewport+'_routes_hydrate_and_render')
            cdp.call('Page.navigate',{'url':'http://127.0.0.1:8080/not-a-real-route'},session)
            until(lambda:'Page not found' in text(session))
            record('production_not_found_route')
            for event in cdp.events:
                params=event.get('params',{})
                if event.get('method')=='Runtime.exceptionThrown':
                    report['runtime_errors'].append(params.get('exceptionDetails'))
                if event.get('method')=='Network.responseReceived':
                    response=params.get('response',{})
                    if '/api/' in response.get('url','') and response.get('status',0)>=400:
                        report['api_errors'].append(dict(url=response['url'],status=response['status']))
            assert not report['runtime_errors'],report['runtime_errors']
            assert not report['api_errors'],report['api_errors']
        except Exception as exc:
            report['failure']=str(exc)
            if cdp:
                report['last_page_text']=text(session)[-6000:]
            raise
        finally:
            (OUTPUT/'production_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            for viewport in images:
                contact_sheet(images[viewport],OUTPUT/f'ui_{viewport}.png',2 if viewport=='desktop' else 5,600 if viewport=='desktop' else 240,380 if viewport=='desktop' else 430)
            if cdp:
                try:cdp.call('Browser.close')
                except Exception:pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    else:process.terminate()
                    process.wait(timeout=15)
            for log in logs:log.close()


if __name__=='__main__':
    main()
