"""Install once, then serve frontend + backend on localhost:8000."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent
BACKEND=ROOT/'backend';FRONTEND=ROOT/'frontend'

def run(args,cwd=ROOT):subprocess.run([str(a) for a in args],cwd=cwd,check=True)
def content_hash(files):
    digest=hashlib.sha256()
    for p in sorted(files,key=lambda x:x.relative_to(ROOT).as_posix()):digest.update(p.relative_to(ROOT).as_posix().encode());digest.update(p.read_bytes())
    return digest.hexdigest()

def main():
    if sys.version_info<(3,11):raise RuntimeError('Python 3.11 이상이 필요합니다.')
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',8000))==0:raise RuntimeError('8000 포트가 사용 중입니다. 기존 FastAPI 실행 창에서 Ctrl+C를 누른 뒤 다시 실행하세요.')
    env_file=BACKEND/'.env'
    if not env_file.exists():
        print('\n처음 실행합니다. 기존 backend/.env를 복사하면 같은 Supabase 계정을 사용합니다.')
        previous=input('기존 .env 파일의 전체 경로(없으면 Enter): ').strip().strip('"')
        if previous:
            source=Path(previous)
            if not source.is_file():raise RuntimeError('입력한 .env 파일을 찾지 못했습니다.')
            shutil.copyfile(source,env_file)
        else:
            mode=input('실제 Supabase 사용: Enter / 내 컴퓨터 시연만: local 입력: ').strip() or 'supabase'
            if mode=='local':env_file.write_text('APP_ENV=development\nAPP_MODE=local\nSQLITE_PATH=nextmeal.local.db\n',encoding='utf-8')
            elif mode=='supabase':
                url=input('Supabase Project URL: ').strip().rstrip('/')
                key=input('Supabase Publishable key: ').strip()
                if not url.startswith('https://') or not key.startswith('sb_publishable_'):raise RuntimeError('실제 URL과 sb_publishable_로 시작하는 키를 입력하세요.')
                if any(ch in url+key for ch in '\r\n'):raise RuntimeError('설정값에 줄바꿈을 넣을 수 없습니다.')
                env_file.write_text(f'APP_ENV=development\nAPP_MODE=supabase\nSUPABASE_URL={url}\nSUPABASE_PUBLISHABLE_KEY={key}\n',encoding='utf-8')
            else:raise RuntimeError('local 또는 Supabase 설정을 선택하세요.')
    marker=ROOT/'.setup';marker.mkdir(exist_ok=True)
    state_file=marker/'installed.json'
    try:state=json.loads(state_file.read_text())
    except (OSError,ValueError):state={}
    venv=BACKEND/'.venv';python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():run([sys.executable,'-m','venv',venv])
    req_hash=content_hash([BACKEND/'requirements.txt'])+sys.version
    if state.get('python')!=req_hash:
        print('\nPython 라이브러리를 설치합니다. 처음 실행할 때 시간이 걸립니다.')
        run([python,'-m','pip','install','-r',BACKEND/'requirements.txt']);state['python']=req_hash
    build_hash=content_hash(list((FRONTEND/'src').rglob('*.*'))+[FRONTEND/'index.html',FRONTEND/'vite.config.js',FRONTEND/'package-lock.json'])
    build_manifest=FRONTEND/'dist/build-manifest.json'
    try:built_hash=json.loads(build_manifest.read_text())['source_hash']
    except (OSError,ValueError,KeyError):built_hash=None
    if built_hash!=build_hash or not (FRONTEND/'dist/index.html').exists():
        npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm');node=shutil.which('node')
        if not npm or not node:raise RuntimeError('프론트 소스가 바뀌었거나 빌드 파일이 없습니다. 다시 빌드하려면 Node.js 22 이상이 필요합니다.')
        version=subprocess.check_output([node,'--version'],text=True).strip()
        if int(version.lstrip('v').split('.')[0])<22:raise RuntimeError('다시 빌드하려면 Node.js 22 이상이 필요합니다. 현재 '+version)
        lock_hash=content_hash([FRONTEND/'package-lock.json'])+version
        if state.get('npm')!=lock_hash or not (FRONTEND/'node_modules').exists():
            print('\n프론트 라이브러리를 설치합니다.')
            run([npm,'ci'],FRONTEND);state['npm']=lock_hash
        run([npm,'run','build'],FRONTEND)
        build_manifest.write_text(json.dumps({'source_hash':build_hash}),encoding='utf-8')
    state_file.write_text(json.dumps(state),encoding='utf-8')
    def open_when_ready():
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=1) as r:
                    if r.status==200:webbrowser.open('http://127.0.0.1:8000');return
            except OSError:time.sleep(1)
    print('\n다음한끼 실행: http://127.0.0.1:8000\n이 창을 켜 두세요. 종료하려면 Ctrl+C를 누르세요.\n')
    process=subprocess.Popen([str(python),'-m','uvicorn','app.serve:create_app','--factory','--env-file','.env','--host','127.0.0.1','--port','8000'],cwd=BACKEND)
    threading.Thread(target=open_when_ready,daemon=True).start()
    try:
        code=process.wait()
        if code:raise RuntimeError('서버 실행이 종료되었습니다. 위 오류 메시지를 확인하세요.')
    except KeyboardInterrupt:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill()

if __name__=='__main__':
    try:main()
    except (RuntimeError,subprocess.CalledProcessError) as error:
        print('\n실행 실패:',error);input('Enter를 누르면 닫습니다.');sys.exit(1)
