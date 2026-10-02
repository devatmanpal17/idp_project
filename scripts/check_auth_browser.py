"""Real React/Chrome account failure checks with SDK doubles; no real sign-ins.

Requires frontend dependencies, Chrome and the existing browser-test Python deps.
Only the Firebase boundary is mocked; the shipped AuthProvider is compiled as-is.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from check_browser import CDP, ROOT, http, until

OUTPUT = Path(os.getenv('CHAI_AUTH_CHECK_OUTPUT', str(ROOT/'benchmarks/results/demo-readiness-20261002/auth')))


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = {'checks': [], 'runtime_errors': []}
    processes, logs = [], []
    cdp = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp = Path(directory)

        def launch(args, name):
            log = (OUTPUT/(name+'.log')).open('w', encoding='utf-8')
            logs.append(log)
            process = subprocess.Popen(args, cwd=ROOT, stdout=log, stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            return process

        def page(flags=None, source='auth', mobile=False):
            target = cdp.call('Target.createTarget', {'url':'about:blank'})['targetId']
            session = cdp.call('Target.attachToTarget', {'targetId':target,'flatten':True})['sessionId']
            for domain in ('Page', 'Runtime'):
                cdp.call(domain+'.enable',session=session)
            if mobile:
                cdp.call('Emulation.setDeviceMetricsOverride', {'width':390,'height':844,'deviceScaleFactor':1,'mobile':True},session)
            # Accelerate only the app's 15-second deadline, not React's timers.
            cdp.call('Page.addScriptToEvaluateOnNewDocument', {'source':f"window.authFlags={json.dumps(flags or {})};const timer=window.setTimeout;window.setTimeout=(fn,ms,...args)=>timer(fn,ms===15000?900:ms,...args);"},session)
            cdp.call('Page.navigate', {'url':f'http://127.0.0.1:8092/{source}.html'},session)
            if source=='auth':
                until(lambda:cdp.evaluate('Boolean(window.authView && !window.authView.loading)',session),5)
            else:
                until(lambda:cdp.evaluate('Boolean(window.configResult)',session),5)
            return session

        def evaluate(expression, session):
            return cdp.evaluate(expression,session)

        def state(session):
            return evaluate('({uid:authView.user?.uid??null,profile:authView.profile,profileLoaded:authView.profileLoaded,loading:authView.loading,error:authView.error,configured:authView.configured})',session)

        def flush(session):
            evaluate('new Promise(resolve=>setTimeout(resolve,80))',session)

        def login(session, uid='Alice'):
            evaluate(f'authSDK.emit(authSDK.user({json.dumps(uid)}))',session)
            until(lambda:evaluate('authSDK.reads.length',session),3)

        def read(session, index=0, name='Alice saved'):
            evaluate(f'authSDK.read({index},{{displayName:{json.dumps(name)},bio:"PRIVATE_PROFILE"}})',session)

        def ready(session):
            until(lambda:not state(session)['loading'],3)

        def save(session):
            evaluate("window.saveResult='pending';authView.saveProfile({displayName:' Edited name ',bio:' Edited bio ',learningGoal:' Study ',preferredLanguage:' '}).then(()=>window.saveResult='saved').catch(e=>window.saveResult=e.message);true",session)

        def check(name, action):
            try:
                result=action()
                report['checks'].append({'name':name,'passed':True,'details':result})
                print(name+': passed',flush=True)
            except Exception as exc:
                report['checks'].append({'name':name,'passed':False,'error':str(exc)})
                print(name+': FAILED: '+str(exc),flush=True)

        try:
            build=[shutil.which('node'),str(ROOT/'tests/auth_browser/build.cjs'),str(temp)]
            if os.getenv('CHAI_AUTH_PROVIDER_SOURCE'):
                build.append(os.environ['CHAI_AUTH_PROVIDER_SOURCE'])
            subprocess.run(build,check=True,cwd=ROOT)
            launch([sys.executable,'-m','http.server','8092','--bind','127.0.0.1','--directory',str(temp)],'http')
            until(lambda:__import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8092/auth.html',timeout=2).status==200,10)
            chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            profile=temp/'chrome'
            launch([str(chrome),'--headless=new','--no-first-run','--disable-background-networking',
                    '--remote-debugging-port=0',f'--user-data-dir={profile}'],'chrome')
            port=until(lambda:(profile/'DevToolsActivePort').read_text().splitlines()[0],15)
            cdp=CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])

            def signed_out_response():
                s=page();login(s)
                evaluate('authView.signOut()',s);read(s);flush(s)
                until(lambda:state(s)['uid'] is None,3)
                assert state(s)['profile'] is None,state(s)
                assert not evaluate('authSDK.writes.length',s),'Stale read wrote old-account metadata'
            check('late_profile_after_sign_out_is_ignored',signed_out_response)

            def switch_response():
                s=page();login(s)
                evaluate('authSDK.emit(authSDK.user("Bob"))',s)
                read(s,1,'Bob saved');ready(s)
                read(s,0,'Alice private');flush(s)
                until(lambda:state(s)['profile']['displayName']=='Bob saved',3)
                assert state(s)['profile']['uid']=='Bob',state(s)
                assert evaluate('authSDK.writes.every(w=>w.uid==="Bob")',s)
            check('out_of_order_accounts_keep_current_profile',switch_response)

            def old_error():
                s=page();login(s);evaluate('authSDK.emit(authSDK.user("Bob"))',s)
                read(s,1,'Bob saved');ready(s)
                evaluate('authSDK.reads[0].reject(new Error("OLD_ACCOUNT_ERROR"))',s)
                flush(s)
                assert state(s)['error'] is None,state(s)
            check('old_account_failure_does_not_replace_current_error',old_error)

            def stalled_read():
                s=page();login(s);ready(s)
                assert 'loaded in time' in state(s)['error'],state(s)
                assert state(s)['profile']['displayName']=='Alice Google',state(s)
                read(s,0,'Late saved data')
                flush(s)
                assert state(s)['profile']['displayName']=='Alice Google',state(s)
            check('stalled_profile_read_recovers_with_identity',stalled_read)

            def rejected_read():
                s=page();login(s);evaluate('authSDK.reads[0].reject(new Error("Permission denied"))',s);ready(s)
                assert state(s)['profile']['uid']=='Alice',state(s)
                assert state(s)['error']=='Permission denied',state(s)
            check('profile_permission_failure_keeps_identity',rejected_read)

            def unavailable_profile_save():
                s=page();login(s);evaluate('authSDK.reads[0].reject(new Error("Permission denied"))',s);ready(s);save(s)
                until(lambda:evaluate('saveResult!=="pending"',s),3)
                assert 'Reload before editing' in evaluate('saveResult',s),state(s)
                assert not state(s)['profileLoaded'],state(s)
                assert evaluate('authSDK.writes.length===0 && authSDK.updates.length===0',s),'Unavailable saved fields were overwritten'
            check('unavailable_profile_cannot_overwrite_saved_fields',unavailable_profile_save)

            def stalled_metadata():
                s=page();login(s);read(s);ready(s)
                assert state(s)['profile']['displayName']=='Alice saved',state(s)
                assert evaluate('authSDK.writes.length===1',s)
                assert evaluate('!("bio" in authSDK.writes[0].data) && !("displayName" in authSDK.writes[0].data)',s)
                until(lambda:bool(state(s)['error']),3)
                assert 'still available' in state(s)['error'],state(s)
            check('stalled_login_write_does_not_block_or_overwrite_form',stalled_metadata)

            def saved_profile():
                s=page();login(s);read(s);ready(s);evaluate('authSDK.writes[0].resolve()',s);save(s)
                until(lambda:evaluate('authSDK.writes.length===2',s),3)
                evaluate('authSDK.writes[1].resolve()',s)
                flush(s)
                until(lambda:evaluate('saveResult==="saved"',s),3)
                assert state(s)['profile']['displayName']=='Edited name',state(s)
                assert state(s)['profile']['preferredLanguage']=='English',state(s)
                assert state(s)['error'] is None,state(s)
            check('successful_profile_save_normalizes_and_confirms',saved_profile)

            def first_profile_save():
                s=page();login(s);evaluate('authSDK.read(0,null)',s);ready(s)
                assert evaluate('authSDK.writes.length===0',s),'Metadata-only creation violates profile rules'
                save(s)
                until(lambda:evaluate('authSDK.writes.length===1',s),3)
                fields=evaluate('authSDK.writes[0].data',s)
                assert fields['uid']=='Alice',fields
                for field,limit in [('displayName',80),('bio',500),('learningGoal',200),('preferredLanguage',40),('email',None),('photoURL',None)]:
                    assert isinstance(fields[field],str),fields
                    assert limit is None or len(fields[field])<=limit,fields
                evaluate('authSDK.writes[0].resolve()',s)
                until(lambda:evaluate('saveResult==="saved"',s),3)
            check('first_profile_save_includes_all_required_rule_fields',first_profile_save)

            def save_timeout():
                s=page();login(s);read(s);ready(s);evaluate('authSDK.writes[0].resolve()',s);save(s)
                until(lambda:evaluate('saveResult!=="pending"',s),3)
                assert 'may still sync' in state(s)['error'],state(s)
                assert state(s)['profile']['displayName']=='Alice saved',state(s)
                evaluate('authSDK.writes[1].resolve()',s)
                assert state(s)['profile']['displayName']=='Alice saved',state(s)
            check('stalled_save_exits_without_false_confirmation',save_timeout)

            def save_switch(deferred=False):
                s=page({'deferUpdate':deferred});login(s);read(s);ready(s);evaluate('authSDK.writes[0].resolve()',s);save(s)
                until(lambda:evaluate('authSDK.updates.length===1' if deferred else 'authSDK.writes.length===2',s),3)
                evaluate('authSDK.emit(authSDK.user("Bob"))',s);read(s,1,'Bob saved');ready(s)
                evaluate('authSDK.updates[0].resolve()' if deferred else 'authSDK.writes[1].resolve()',s)
                until(lambda:evaluate('saveResult!=="pending"',s),3)
                assert state(s)['profile']['uid']=='Bob' and state(s)['profile']['displayName']=='Bob saved',state(s)
                assert 'account changed' in evaluate('saveResult',s),evaluate('saveResult',s)
                assert state(s)['error'] is None,state(s)
                if deferred:
                    assert evaluate('authSDK.writes.filter(w=>"bio" in w.data).length===0',s),'Old account write started after account changed'
            check('late_save_does_not_mutate_new_account',save_switch)
            check('account_switch_stops_next_save_step',lambda:save_switch(True))

            def blocked_storage():
                s=page({'blockStorage':True})
                evaluate('authView.signInWithGoogle()',s)
                assert evaluate('authSDK.persistence.includes("memory") && authSDK.popups===1',s)
                assert state(s)['error'] is None,state(s)
            check('blocked_storage_uses_memory_sign_in',blocked_storage)

            def popup_mobile():
                s=page(mobile=True);evaluate('authView.signInWithGoogle()',s)
                assert evaluate('authSDK.popups===1',s)
            check('mobile_and_loopback_sign_in_keep_current_origin',popup_mobile)

            def invalid_setup():
                s=page({'badConfig':True})
                assert not state(s)['configured'],state(s)
                assert state(s)['error']=='invalid configuration',state(s)
                assert not state(s)['loading'],state(s)
            check('invalid_firebase_setup_is_recoverable',invalid_setup)

            def persistence_timeout():
                s=page({'hangPersistence':True})
                evaluate('authView.signInWithGoogle().catch(()=>{})',s)
                assert 'Sign-in setup timed out' in state(s)['error'],state(s)
                assert evaluate('authSDK.popups===0',s)
            check('stalled_persistence_exits_sign_in',persistence_timeout)

            def stalled_auth_state():
                s=page({'hangAuthState':True})
                assert 'Sign-in state could not be checked' in state(s)['error'],state(s)
                login(s);read(s);ready(s)
                assert state(s)['profile']['uid']=='Alice',state(s)
                assert state(s)['error'] is None,state(s)
            check('stalled_auth_initialization_can_recover',stalled_auth_state)

            def unmount():
                s=page();login(s);evaluate('unmountAuth()',s);read(s);flush(s)
                assert evaluate('authSDK.listeners.size===0 && authSDK.writes.length===0',s)
            check('unmount_unsubscribes_and_ignores_late_load',unmount)

            def config_optional():
                s=page(source='config')
                result=evaluate('({...configResult,initialized:configSDK.initialized})',s)
                assert result=={'configured':True,'appName':'[DEFAULT]','reused':True,'initialized':1},result
            check('auth_configuration_allows_optional_storage_fields_and_named_apps',config_optional)
            check('missing_required_configuration_disables_auth',lambda:assert_missing(page(source='config-missing'),evaluate))

            cdp.call('Browser.getVersion')
            report['runtime_errors']=[event['params']['exceptionDetails'].get('text','') for event in cdp.events if event.get('method')=='Runtime.exceptionThrown']
        finally:
            if cdp:
                try:cdp.call('Browser.close')
                except Exception:pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    else:process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        # Windows Chrome may take longer to exit under parallel
                        # browser tests; terminate the owned process handle.
                        process.kill()
                        process.wait(timeout=10)
            for log in logs:log.close()
            (OUTPUT/'auth_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    failures=[item for item in report['checks'] if not item['passed']]
    print(json.dumps({'checks':len(report['checks']),'failures':len(failures),'runtime_errors':len(report['runtime_errors'])}),flush=True)
    return 1 if failures or report['runtime_errors'] else 0


def assert_missing(session,evaluate):
    assert evaluate('configResult.configured===false',session)


if __name__=='__main__':
    raise SystemExit(main())
