"""Check real decoded-video observation and seek gaps in isolated Chrome."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import imageio_ffmpeg

from check_browser import CDP, ROOT, http, until

OUTPUT = ROOT/'benchmarks/results/demo-readiness-20261002/observation'


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    processes,logs=[],[]
    cdp=None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp=Path(directory)
        def launch(args,name):
            log=(OUTPUT/(name+'.log')).open('w',encoding='utf-8');logs.append(log)
            process=subprocess.Popen(args,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            processes.append(process)
        try:
            shutil.copyfile(ROOT/'extension/observation.js',temp/'observation.js')
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-f','lavfi',
                '-i','testsrc=size=640x360:rate=10:duration=12','-c:v','libvpx-vp9','-b:v','0','-crf','40','-an','-y',str(temp/'fixture.webm')],check=True,capture_output=True)
            (temp/'index.html').write_text('''<!doctype html><video muted controls width="640" height="360"></video>
<script src="observation.js"></script><script>
window.checkPlayback=async()=>{
 const video=document.querySelector('video');
 video.src=URL.createObjectURL(await fetch('fixture.webm').then(response=>response.blob()));video.load();
 if(video.readyState<2) await new Promise(resolve=>video.addEventListener('loadeddata',resolve,{once:true}));
 const trace=[],events=[];
 for(const name of ['play','pause','seeking','seeked','ratechange','waiting','stalled','ended']) video.addEventListener(name,()=>events.push({name,media:video.currentTime,wall:performance.now()}));
 const request=video.requestVideoFrameCallback.bind(video);
 video.requestVideoFrameCallback=fn=>request((now,metadata)=>{
   trace.push({now,...metadata,currentTime:video.currentTime,rate:video.playbackRate,paused:video.paused,seeking:video.seeking,readyState:video.readyState,hidden:document.hidden});fn(now,metadata);
 });
 const observation=ChaiObservation.attach(video);
 await video.play();await new Promise(resolve=>setTimeout(resolve,2900));video.pause();
 const first=observation.tracker.intervals.map(pair=>[...pair]);
 video.currentTime=8;await new Promise(resolve=>video.addEventListener('seeked',resolve,{once:true}));
 await video.play();await new Promise(resolve=>setTimeout(resolve,2300));video.pause();
 observation.detach();
 return {first,intervals:observation.tracker.intervals,openingCovered:observation.tracker.covers(500,1500),endingCovered:observation.tracker.covers(8500,9500),skippedCovered:observation.tracker.covers(4000,5000),trace,events};
};</script>''',encoding='utf-8')
            launch([sys.executable,'-m','http.server','8094','--bind','127.0.0.1','--directory',str(temp)],'http')
            until(lambda:__import__('urllib.request',fromlist=['urlopen']).urlopen('http://127.0.0.1:8094',timeout=2).status==200,10)
            chrome=Path(os.environ.get('PROGRAMFILES','C:/Program Files'))/'Google/Chrome/Application/chrome.exe'
            profile=temp/'chrome'
            launch([str(chrome),'--headless=new','--no-first-run','--disable-background-networking','--remote-debugging-port=0',f'--user-data-dir={profile}'],'chrome')
            port=until(lambda:(profile/'DevToolsActivePort').read_text().splitlines()[0],15)
            cdp=CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])
            session=cdp.page('http://127.0.0.1:8094')
            until(lambda:cdp.evaluate('typeof checkPlayback==="function"',session),10)
            result=cdp.evaluate('checkPlayback()',session)
            (OUTPUT/'observation_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print({key:value for key,value in result.items() if key not in ('trace','events')},flush=True)
            return 0 if result['openingCovered'] and result['endingCovered'] and not result['skippedCovered'] else 1
        finally:
            if cdp:
                try:cdp.call('Browser.close')
                except Exception:pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    if os.name=='nt':subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    else:process.terminate()
                    try:process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill();process.wait(timeout=10)
            for log in logs:log.close()


if __name__=='__main__':
    raise SystemExit(main())
