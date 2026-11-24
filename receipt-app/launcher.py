"""Start one local Tally server and open it in the default browser."""
import json
import os
import signal
import socket
import runpy
import threading
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
    print('Receipt app: '+URL,flush=True)
    print('Keep this window open. Press Ctrl+C or close this window to stop the server.',flush=True)
    launch_foreground()


def open_when_ready():
    for _ in range(100):
        current=health()
        if current and current.get('app')=='tally-local' and current.get('workspace')==str(ROOT) and current.get('pid')==os.getpid():
            webbrowser.open(URL);return
        time.sleep(.2)
    print('Browser opening timed out. Check the server messages in this window.',flush=True)


def launch_foreground():
    # The server shares this console and process; there is no detached child.
    threading.Thread(target=open_when_ready,daemon=True).start()
    try:
        runpy.run_path(str(ROOT/'app.py'),run_name='__main__')
    except KeyboardInterrupt:
        print('\nReceipt app stopped.',flush=True)


def port_in_use():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
        connection.settimeout(.3)
        return connection.connect_ex(('127.0.0.1',5050))==0


if __name__=='__main__':main()
