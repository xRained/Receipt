"""Start one local Tally server and open it in the default browser."""
import json
import os
import signal
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
    if current and current.get('app')=='tally-local' and current.get('workspace')==str(ROOT):
        if current.get('version')==expected_version:webbrowser.open(URL);return
        pidfile=ROOT/'data'/'server.pid'
        if pidfile.exists() and int(pidfile.read_text())==current.get('pid'):
            os.kill(current['pid'],signal.SIGTERM)
            time.sleep(.5)
        else:raise RuntimeError('Close the existing Tally server window, then run start.bat again.')
    elif current:raise RuntimeError('Another app is serving port 5050. Close it before starting Tally.')
    (ROOT/'data').mkdir(exist_ok=True)
    with open(ROOT/'data'/'server.log','ab') as out,open(ROOT/'data'/'server-error.log','ab') as err:
        subprocess.Popen([sys.executable,str(ROOT/'app.py')],cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    for _ in range(100):
        current=health()
        if current and current.get('version')==expected_version:webbrowser.open(URL);return
        time.sleep(.2)
    raise RuntimeError('The server did not start. See data/server-error.log.')


if __name__=='__main__':main()
