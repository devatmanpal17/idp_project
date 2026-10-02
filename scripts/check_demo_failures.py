"""Chrome failure-injection checks; isolated profile, mocked API, no user data/models."""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from check_browser import CDP, ROOT, http, until

OUTPUT = ROOT / 'benchmarks/results/demo-readiness-20261002'
EMPTY = dict(courses=[], topics=[], quizzes=[], study_events=[], recommendations=[], activity_log=[], history=[])
MOCK = """
window.demoData = %s;
window.demoTopics = [];
window.demoRequests = [];
window.demoQuizAborts = 0;
window.demoQuizInvalid = false;
const nativeFetch = window.fetch;
window.fetch = async (url, init) => {
  if (!String(url).includes('/api/')) return nativeFetch(url, init);
  const path = String(url).split('/api/')[1];
  window.demoRequests.push(path);
  let value = {};
  if (path === 'learning/data') value = window.demoData;
  if (path === 'rag/topics') value = {topics:window.demoTopics};
  if (path === 'health') value = {status:'setup_required',indexed_chunks:0};
  if (path === 'rag/generate-quiz' && !window.demoQuizInvalid) return new Promise((resolve,reject) => {
    init.signal.addEventListener('abort',()=>{window.demoQuizAborts++;reject(new DOMException('Aborted','AbortError'))},{once:true});
  });
  if (path === 'rag/ask') return new Promise((resolve,reject) => {
    init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
  });
  return new Response(JSON.stringify(value),{headers:{'Content-Type':'application/json'}});
};
""" % json.dumps(EMPTY)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = []
    processes, logs = [], []
    cdp = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        def launch(args, name, cwd=ROOT):
            log = (OUTPUT / f'{name}.log').open('w', encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen(args, cwd=cwd, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
        def page(script='', route='/quizzes'):
            target = cdp.call('Target.createTarget', {'url':'about:blank'})['targetId']
            session = cdp.call('Target.attachToTarget', {'targetId':target,'flatten':True})['sessionId']
            for domain in ('Page','Runtime'):
                cdp.call(domain+'.enable', session=session)
            cdp.call('Page.addScriptToEvaluateOnNewDocument', {'source':MOCK+'\n'+script}, session)
            cdp.call('Page.navigate', {'url':'http://127.0.0.1:8082'+route}, session)
            until(lambda: cdp.evaluate("Boolean(document.querySelector('button'))", session), 30)
            # Wait for React hydration/effects, not just server HTML.
            until(lambda: cdp.evaluate("Object.keys(document.querySelector('button')).some(k=>k.startsWith('__reactFiber')) || document.body.innerText.includes('page didn')", session), 30)
            return session
        def check(name, action):
            try:
                details = action()
                report.append(dict(name=name,passed=True,details=details))
                print(name+': passed',flush=True)
            except Exception as exc:
                report.append(dict(name=name,passed=False,error=str(exc)))
                print(name+': FAILED: '+str(exc),flush=True)
        def click(selector, session):
            cdp.evaluate(f"document.querySelector({json.dumps(selector)}).click()", session)
        def text(session):
            return cdp.evaluate('document.body.innerText', session)
        def open_chat(session):
            click('[aria-label="Open personal assistant"]', session)
            until(lambda: cdp.evaluate("document.querySelector('[aria-label=\"Message Chai\"]')?.getBoundingClientRect().height > 0",session))
        def healthy_chat(script):
            session = page(script)
            until(lambda: 'Assessment Quizzes' in text(session), 5)
            open_chat(session)
            cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('What can you help')).click()", session)
            until(lambda:'I can answer questions' in text(session),5)
            click('[aria-label="Start a new chat"]', session)
            click('[title="Change theme"]', session)
            assert 'Assessment Quizzes' in text(session), text(session)[-1000:]
            return 'Chat, reset and theme remain usable'
        try:
            launch([shutil.which('node'), str(ROOT/'frontend/node_modules/vite/bin/vite.js'),
                    '--host','127.0.0.1','--port','8082','--strictPort'], 'frontend', ROOT/'frontend')
            until(lambda: __import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8082',timeout=3).status==200)
            chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            profile=temp/'chrome'
            launch([str(chrome),'--headless=new','--no-first-run','--disable-background-networking',
                    '--remote-debugging-port=0',f'--user-data-dir={profile}'], 'chrome')
            port=until(lambda:(profile/'DevToolsActivePort').read_text().splitlines()[0])
            cdp=CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])
            check('corrupt_chat_entries',lambda:healthy_chat("localStorage.setItem('chaigaram-assistant-messages', '[null,{\"id\":\"bad\",\"role\":\"assistant\",\"text\":{}},{\"id\":\"bad2\",\"role\":\"user\",\"text\":\"x\",\"sources\":[null]}]');"))
            check('blocked_storage',lambda:healthy_chat("for(const key of ['getItem','setItem','removeItem']) Storage.prototype[key]=()=>{throw new DOMException('Blocked','SecurityError')};"))
            check('full_storage',lambda:healthy_chat("Storage.prototype.setItem=()=>{throw new DOMException('Full','QuotaExceededError')};"))
            check('invalid_chat_json',lambda:healthy_chat("localStorage.setItem('chaigaram-assistant-messages','{broken');"))
            def partial_history():
                s=page("localStorage.setItem('chaigaram-assistant-messages',JSON.stringify([null,{id:'saved',role:'assistant',text:'VALID_SAVED_CHAT'}]));")
                until(lambda:'Assessment Quizzes' in text(s))
                open_chat(s)
                until(lambda:'VALID_SAVED_CHAT' in text(s))
            check('valid_chat_survives_partial_corruption',partial_history)
            session=page()
            until(lambda:'Assessment Quizzes' in text(session))
            def api_cases():
                result=cdp.evaluate("""(async()=>{
                  const {apiJSON}=await import('/src/lib/api.ts');
                  const previous=window.fetch; const results={};
                  try {
                    window.fetch=(_,init)=>new Promise((resolve,reject)=>init.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError'))));
                    const controller=new AbortController(); const pending=apiJSON('/test',{signal:controller.signal}); controller.abort();
                    try {await pending} catch(e) {results.cancel=e.name}
                    try {await apiJSON('/test',undefined,40)} catch(e) {results.timeout=e.message}
                    window.fetch=async()=>new Response('<html>Wrong server</html>',{status:200});
                    try {await apiJSON('/test')} catch(e) {results.invalid=e.message}
                    window.fetch=async()=>new Response(JSON.stringify({detail:[{loc:['body','topic'],msg:'Field required'}]}),{status:422});
                    try {await apiJSON('/test')} catch(e) {results.validation=e.message}
                  } finally {window.fetch=previous}
                  return results;
                })()""",session)
                assert result.get('cancel')=='AbortError',result
                assert 'timed out' in result.get('timeout','').lower(),result
                assert 'json' in result.get('invalid','').lower(),result
                assert 'topic' in result.get('validation',''),result
                return result
            check('api_cancellation_timeout_invalid_json_validation',api_cases)
            def invalid_payloads():
                results=cdp.evaluate("""(async()=>{
                  const client=await import('/src/lib/ai-client.ts'); const old=window.fetch; const results=[];
                  window.fetch=async()=>new Response('{}',{headers:{'Content-Type':'application/json'}});
                  try {
                    for (const task of [()=>client.askRAGAssistant({question:'test'}),()=>client.evaluateRAGQuiz({quiz_id:'bad',topic:'test',given_answers:[]}),()=>client.fetchIndexedTopics()]) {
                      try {await task();results.push('accepted')} catch(e) {results.push(e.message)}
                    }
                  } finally {window.fetch=old}
                  return results;
                })()""",session)
                assert all('invalid' in value.lower() for value in results),results
                return results
            check('invalid_assistant_assessment_topics_payloads_rejected',invalid_payloads)
            def empty_topics():
                button=cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Generate New AI')).disabled",session)
                assert button is True,'Generation allowed without indexed evidence'
            check('empty_evidence_disables_generation',empty_topics)
            def health_label():
                assert 'AI setup required' in text(session),text(session)[:1200]
            check('reachable_backend_is_not_labelled_offline',health_label)
            def cancel_chat():
                open_chat(session)
                cdp.evaluate("document.querySelector('[aria-label=\"Message Chai\"]').focus()", session)
                cdp.call('Input.insertText', {'text':'Explain red black tree invariants'},session)
                click('[aria-label="Send message"]',session)
                until(lambda:cdp.evaluate("Boolean(document.querySelector('[aria-label=\"Stop response\"]'))",session))
                click('[aria-label="Stop response"]',session)
                until(lambda:'I stopped that response.' in text(session),5)
                assert 'engine is offline' not in text(session),text(session)[-1000:]
            check('chat_stop_feedback',cancel_chat)
            def chat_timeout():
                s=page("const originalTimer=window.setTimeout;window.setTimeout=(action,ms,...args)=>originalTimer(action,ms===60000?40:ms,...args);")
                until(lambda:'Assessment Quizzes' in text(s))
                open_chat(s)
                click('[aria-label="Start a new chat"]',s)
                cdp.evaluate("document.querySelector('[aria-label=\"Message Chai\"]').focus()",s)
                cdp.call('Input.insertText',{'text':'Explain red black tree properties'},s)
                click('[aria-label="Send message"]',s)
                until(lambda:'The response timed out.' in text(s),5)
                assert 'I stopped that response.' not in text(s)
            check('chat_timeout_is_distinct_from_stop',chat_timeout)
            def generation_case(invalid=False):
                s=page("window.demoTopics=['Demo topic'];window.demoQuizInvalid="+str(invalid).lower()+';')
                until(lambda:cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Generate New AI')).disabled===false",s))
                cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Generate New AI')).click()",s)
                until(lambda:cdp.evaluate("window.demoRequests.includes('rag/generate-quiz')",s))
                if invalid:
                    until(lambda:'invalid quiz response' in text(s).lower(),5)
                    assert 'Assessment Quizzes' in text(s) and 'Retry generation' in text(s)
                else:
                    before=cdp.evaluate('window.demoQuizAborts',s)
                    cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Close').click()",s)
                    until(lambda:cdp.evaluate(f'window.demoQuizAborts>{before}',s),5)
            check('closing_generator_aborts_pending_request',generation_case)
            check('malformed_quiz_response_is_recoverable',lambda:generation_case(True))
            def stale_quiz():
                seed=dict(EMPTY)
                seed['topics']=[dict(id='t1',title='Demo topic',course_id='c1',mastery_score=0)]
                seed['quizzes']=[dict(id='q1',topic_id='t1',course_id='c1',score=0,completed_at='2026-10-02T10:00:00Z',question_type='mcq',questions=[dict(q='DELETED_QUIZ_SENTINEL',answer='A',given='B',correct=False,explanation='Demo feedback')])]
                s=page('window.demoData='+json.dumps(seed)+";window.demoTopics=['Demo topic'];")
                until(lambda:'DELETED_QUIZ_SENTINEL' in text(s))
                cdp.evaluate('window.demoData='+json.dumps(EMPTY)+';window.demoTopics=[];',s)
                until(lambda:'0 completed sessions' in text(s),25)
                assert 'DELETED_QUIZ_SENTINEL' not in text(s),'Deleted quiz remains visible after refresh'
                until(lambda:cdp.evaluate("[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Generate New AI')).disabled",s),20)
            check('deleted_quiz_and_topic_refresh',stale_quiz)
        finally:
            (OUTPUT/'failure_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            if cdp:
                try: cdp.call('Browser.close')
                except Exception: pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name=='nt': subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    else: process.terminate()
                    process.wait(timeout=15)
            for log in logs: log.close()
    if any(not result['passed'] for result in report):
        raise SystemExit(1)


if __name__=='__main__':
    main()
