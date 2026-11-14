"""One origin for the built frontend and API. No frontend .env is required."""
import base64
import json
import os
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from .main import create_app as api_app

def create_app():
    app=api_app()
    mode=os.getenv('APP_MODE','supabase')
    key=os.getenv('SUPABASE_PUBLISHABLE_KEY','')
    if mode=='supabase':
        if not key.startswith('sb_publishable_'):
            try:
                role=json.loads(base64.urlsafe_b64decode(key.split('.')[1]+'==='))['role']
                if role!='anon':raise ValueError()
            except Exception:raise RuntimeError('프론트에는 Publishable 또는 anon key만 사용할 수 있습니다.')
    @app.get('/app-config',include_in_schema=False)
    def config():return {'mode':mode,'url':os.getenv('SUPABASE_URL','') if mode=='supabase' else '', 'key':key if mode=='supabase' else '', 'api':''}
    dist=Path(__file__).resolve().parents[2]/'frontend'/'dist'
    if dist.exists():app.mount('/',StaticFiles(directory=dist,html=True),name='frontend')
    return app
