"""Start one local Tally server and open it in the default browser."""
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:5050'


def health():
    try:
        with urllib.request.urlopen(URL+'/api/health',timeout=2) as response:return json.load(response)
    except Exception:return None


def main():
    from version import version
    expected_version=version()
    current=health()
    if current and current.get('app')=='tally-local' and Path(current.get('workspace','')).resolve()==ROOT:
        pid=current.get('pid')
        if type(pid) is not int or pid<=0:raise RuntimeError('The running app returned an invalid process ID.')
        # Always restart this workspace, even when its code version is unchanged.
        # A PID file may be stale after copying data from another computer.
        os.kill(pid,signal.SIGTERM)
        for _ in range(50):
            if not port_in_use():break
            time.sleep(.1)
        else:raise RuntimeError('The existing app did not release port 5050. Try again after it closes.')
    elif current:raise RuntimeError('Another app is serving port 5050. Close it before starting Tally.')
    if port_in_use():raise RuntimeError('Port 5050 is occupied by an unrecognized process. Close it before starting Tally.')
    (ROOT/'data').mkdir(exist_ok=True)
    with open(ROOT/'data'/'server.log','ab') as out,open(ROOT/'data'/'server-error.log','ab') as err:
        process=subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(100):
        current=health()
        if current and current.get('app')=='tally-local' and current.get('workspace')==str(ROOT) and current.get('pid')==process.pid and current.get('version')==expected_version:webbrowser.open(URL);return
        if process.poll() is not None:break
        time.sleep(.2)
    raise RuntimeError('The server did not start. See data/server-error.log.')


def port_in_use():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
        connection.settimeout(.3)
        return connection.connect_ex(('127.0.0.1',5050))==0


if __name__=='__main__':main()
