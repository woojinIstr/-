"""Reproducible response-size comparison using temporary local test data only."""
import json
from pathlib import Path
import sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from app.main import create_app,DEMO_USER
from uuid import uuid4

def main():
 with tempfile.TemporaryDirectory() as tmp,TestClient(create_app('local',tmp+'/benchmark.db')) as client:
  client.get('/v3/workspace')
  repo=client.app.state.workspace_repository;revision,document=repo.load(DEMO_USER,'')
  document['history']=[{'id':str(uuid4()),'at':'2026-11-13T00:00:00Z','action':'lot.use','summary':'응답 크기 측정을 위한 가상 이력 '+str(i)} for i in range(500)]
  repo.put(DEMO_USER,'',revision,document)
  body={'request_id':str(uuid4()),'expected_revision':revision+1,'action':'ingredient.create','payload':{'name':'벤치마크용 당근','unit':'g'}}
  old=client.post('/v3/preview',json=body);new=client.post('/v3/preview?compact=true',json=body)
  old.raise_for_status();new.raise_for_status()
  print(json.dumps({'fixture':'temporary local account, 500 history entries','legacy_preview_bytes':len(old.content),'compact_preview_bytes':len(new.content),'reduction_percent':round((1-len(new.content)/len(old.content))*100,2),'note':'Response sizes only; not actual Supabase latency.'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
