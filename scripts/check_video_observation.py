"""Focused real Chrome playback/seek acceptance check in isolated local stores."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import imageio_ffmpeg
from check_browser import CDP, http, until

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = Path(os.getenv('CHAI_VIDEO_CHECK_OUTPUT', str(ROOT / 'benchmarks/results/video-check')))
    output.mkdir(parents=True, exist_ok=True)
    report = {}
    processes, logs = [], []
    cdp = None
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        env = os.environ.copy()
        env.update(DATABASE_URL=f'sqlite:///{(temp / "analytics.db").as_posix()}',
                   CHROMA_PERSIST_DIR=str(temp / 'chroma'))

        def launch(command, name):
            stream = (output / f'{name}.log').open('w', encoding='utf-8')
            logs.append(stream)
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stream, stderr=stream,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            processes.append(process)
            return process

        try:
            launch([sys.executable, '-m', 'uvicorn', 'backend.app:app', '--port', '8001'], 'backend')
            until(lambda: http('http://127.0.0.1:8001/api/health'))
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-hide_banner', '-loglevel', 'error',
                '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=10:duration=12',
                '-c:v', 'libvpx-vp9', '-b:v', '0', '-crf', '40', '-an', '-y',
                str(temp / 'fixture.webm')], check=True, capture_output=True)
            (temp / 'video.html').write_text('''<html><head><title>Observation test</title></head>
<body><h1>Observation test video</h1><video muted controls width="640" height="360" preload="auto"></video>
<script>
async function prepareVideo() {
 const video=document.querySelector('video');
 window.frameSamples=[];
 video.requestVideoFrameCallback(function recordFrame(now,metadata){
   window.frameSamples.push({now,mediaTime:metadata.mediaTime,
     presentationTime:metadata.presentationTime,expectedDisplayTime:metadata.expectedDisplayTime,
     presentedFrames:metadata.presentedFrames});
   video.requestVideoFrameCallback(recordFrame);
 });
 video.src=URL.createObjectURL(await fetch('fixture.webm').then(r=>r.blob()));
 const track=video.addTextTrack('captions','English','en');track.mode='showing';
 track.addCue(new VTTCue(.5,1.5,'Observed opening phrase about sorted sequences.'));
 track.addCue(new VTTCue(4,5,'Skipped secret is a copper lantern.'));
 track.addCue(new VTTCue(8.5,9.5,'Observed ending phrase about binary search.'));
 await new Promise((resolve,reject)=>{
   video.addEventListener('loadeddata',resolve,{once:true});
   video.addEventListener('error',()=>reject(new Error(video.error?.message)),{once:true});
   video.load();
 });
}
</script></body></html>''', encoding='utf-8')
            launch([sys.executable, '-m', 'http.server', '8091', '--bind', '127.0.0.1',
                    '--directory', str(temp)], 'fixture')
            chrome = Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe'
            profile = temp / 'browser'
            launch([str(chrome), '--headless=new', '--no-first-run', '--no-default-browser-check',
                    '--disable-background-networking', '--enable-unsafe-extension-debugging',
                    '--remote-debugging-port=0', f'--user-data-dir={profile}'], 'chrome')
            port = until(lambda: (profile / 'DevToolsActivePort').read_text().splitlines()[0])
            cdp = CDP(http(f'http://127.0.0.1:{port}/json/version')['webSocketDebuggerUrl'])
            extension = cdp.call('Extensions.loadUnpacked', {'path': str(ROOT / 'extension')})['id']
            options = cdp.page(f'chrome-extension://{extension}/options.html')
            until(lambda: cdp.evaluate('Boolean(globalThis.chrome?.storage?.sync)', options))
            cdp.evaluate("chrome.storage.sync.set({apiBaseUrl:'http://127.0.0.1:8001',autoCapture:true})", options)
            page = cdp.page('http://127.0.0.1:8091/video.html')
            until(lambda: cdp.evaluate('typeof prepareVideo === "function"', page))
            cdp.evaluate('prepareVideo()', page)
            time.sleep(1)
            cdp.evaluate("""(() => { const video=document.querySelector('video');
              const seek=()=>{ if(video.currentTime>=2){video.removeEventListener('timeupdate',seek);
                video.pause();window.seekFrom=video.currentTime;
                video.addEventListener('seeked',()=>{window.seekTo=video.currentTime;video.play()},{once:true});
                video.currentTime=8;}};
              video.addEventListener('timeupdate',seek);video.play();})()""", page)
            until(lambda: cdp.evaluate('document.querySelector("video").currentTime>10', page))
            cdp.evaluate('document.querySelector("video").pause()', page)
            report['player'] = cdp.evaluate("""({seekFrom:window.seekFrom,seekTo:window.seekTo,
              mediaTime:document.querySelector('video').currentTime,visibility:document.visibilityState,
              status:document.getElementById('chaigaram-extension-root')?.shadowRoot?.getElementById('status')?.textContent})""", page)
            report['frame_samples'] = cdp.evaluate('window.frameSamples', page)
            (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                diagnostics = http('http://127.0.0.1:8001/api/vectors/diagnostics')
                report['diagnostics'] = diagnostics
                docs = diagnostics['documents']
                if docs and docs[0]['counts'].get('ACTIVE', 0) >= 2:
                    break
                time.sleep(2)
            print(json.dumps(report, indent=2), flush=True)
            assert docs and docs[0]['counts'].get('ACTIVE', 0) >= 2, 'Watched cues did not both activate.'
            doc = docs[0]
            result = http('http://127.0.0.1:8001/api/rag/retrieve',
                          {'query': 'secret copper lantern', 'document_id': doc['document_id']})
            assert 'copper lantern' not in json.dumps(result['chunks'])
            assert not any(a <= 4000 and b >= 5000 for a, b in doc['observed_intervals'])
            report['passed'] = True
        except Exception as exc:
            report.update(passed=False, failure=str(exc))
            raise
        finally:
            (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            if cdp:
                try: cdp.call('Browser.close')
                except Exception: pass
                cdp.socket.close()
            for process in reversed(processes):
                if process.poll() is None:
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                    process.wait(timeout=15)
            for stream in logs: stream.close()


if __name__ == '__main__':
    main()
