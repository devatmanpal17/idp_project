"""Run the built Render dashboard behind the actual nginx gateway for browser QA.

Windows downloads nginx into disposable test storage, without installing it. The
Linux Docker smoke suite separately checks bcrypt, supervision and persistent disks.
"""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import urllib.request
import zipfile

from check_browser import ROOT


def launch_preview(launch, temp: Path):
    if os.name != 'nt':
        raise RuntimeError('Use the Linux Docker smoke suite on Linux.')
    archive = temp/'nginx.zip'
    urllib.request.urlretrieve('https://nginx.org/download/nginx-1.30.5.zip', archive)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.namelist():
            resolved = (temp/entry).resolve()
            if not resolved.is_relative_to(temp.resolve()):
                raise RuntimeError('Unsafe nginx archive path.')
        bundle.extractall(temp)
    nginx = temp/'nginx-1.30.5'
    password = secrets.token_urlsafe(32)
    # Windows nginx lacks system bcrypt; use its supported SHA format for this
    # disposable test password. Production uses htpasswd bcrypt on Linux.
    passwd = temp/'test.htpasswd'
    passwd.write_text('demo:{SHA}'+base64.b64encode(hashlib.sha1(password.encode()).digest()).decode()+'\n')
    config = (ROOT/'deploy/render/nginx.conf.template').read_text()
    import sys
    sys.path.insert(0, str(ROOT))
    from deploy.render.package_extension import package_extension
    download = temp/'extension.zip'
    package_extension(ROOT/'extension', download)
    config = config.replace('/app/chaigaram-extension.zip', f'"{download.as_posix()}"')
    config = config.replace('user www-data;\n', '')
    config = config.replace('listen __PORT__;', 'listen 127.0.0.1:8080;')
    config = config.replace('/etc/nginx/mime.types', f'"{(nginx/"conf/mime.types").as_posix()}"')
    replacements = {'/tmp/chaigaram-nginx.pid': temp/'nginx.pid',
                    '/dev/stderr': temp/'nginx-error.log',
                    '/tmp/chaigaram-client': temp/'nginx-client',
                    '/tmp/chaigaram-proxy': temp/'nginx-proxy',
                    '/tmp/chaigaram.htpasswd': passwd}
    for token, path in replacements.items():
        config = config.replace(token, f'"{path.as_posix()}"')
    target = temp/'nginx.conf'
    target.write_text(config)
    # Copy output away from source/node_modules to prove it is standalone.
    output = temp/'dashboard'
    shutil.copytree(ROOT/'frontend/dist-render', output)
    node = launch([shutil.which('node'), str(output/'server/index.mjs')], 'render-dashboard',
                  extra_env={'NITRO_HOST':'127.0.0.1', 'NITRO_PORT':'3000'})
    launch([str(nginx/'nginx.exe'), '-p', nginx.as_posix()+'/', '-c', target.as_posix(),
            '-g', 'daemon off;'], 'render-gateway')
    return node, {'Authorization':'Basic '+base64.b64encode(('demo:'+password).encode()).decode()}
