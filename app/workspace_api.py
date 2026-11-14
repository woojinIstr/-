"""Versioned atomic workspace API for the integrated MVP."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from contextvars import copy_context
from copy import deepcopy
import json
import sqlite3
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from pydantic import Field, ValidationError
from .workspace import Model, MODELS, apply, bootstrap, fingerprint, inventory_changes, present, shopping
from .timing import measure

class Command(Model):
    request_id: UUID
    expected_revision: int = Field(strict=True, ge=0)
    action: Literal[tuple(MODELS)]
    payload: dict

class Repository:
    def __init__(self, legacy, mode):
        self.legacy, self.mode = legacy, mode
        if mode=='local':
            with closing(sqlite3.connect(legacy.path)) as c:
                c.execute('CREATE TABLE IF NOT EXISTS nextmeal_workspaces(user_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL)');c.commit()

    def get(self, owner, token):
        if self.mode=='local':
            with closing(sqlite3.connect(self.legacy.path)) as c:
                row=c.execute('SELECT revision,document FROM nextmeal_workspaces WHERE user_id=?',(owner,)).fetchone()
            return (row[0],json.loads(row[1])) if row else None
        rows=self.legacy.call('GET','/rest/v1/nextmeal_workspaces',token,params={'select':'revision,document','user_id':'eq.'+owner})
        return (rows[0]['revision'],rows[0]['document']) if rows else None

    def put(self, owner, token, revision, document):
        if len(json.dumps(document,ensure_ascii=False).encode())>8*1024*1024: raise HTTPException(422,'시연용 계정 저장 용량 8MB를 초과했습니다.')
        if self.mode=='local':
            with closing(sqlite3.connect(self.legacy.path,timeout=15)) as c:
                c.execute('BEGIN IMMEDIATE')
                if revision==-1:
                    cursor=c.execute('INSERT OR IGNORE INTO nextmeal_workspaces VALUES (?,0,?)',(owner,json.dumps(document,ensure_ascii=False)))
                else:
                    cursor=c.execute('UPDATE nextmeal_workspaces SET revision=revision+1,document=? WHERE user_id=? AND revision=?',(json.dumps(document,ensure_ascii=False),owner,revision))
                success=cursor.rowcount==1;c.commit();return success
        result=self.legacy.call('POST','/rest/v1/rpc/nextmeal_workspace_put',token,json={'p_expected_revision':revision,'p_document':document})
        return result.get('saved',False)

    def legacy_list(self, table, token, owner=None):
        rows=[];offset=0
        while True:
            params={'limit':'100','offset':str(offset),'order':{'ingredients':'ingredient_id','recipes':'recipe_id','recipe_ingredients':'recipe_id,ingredient_id','inventory':'inventory_id','meals':'meal_id'}[table]}
            if owner: params['user_id']='eq.'+owner
            chunk=self.legacy.request('GET',table,token,params);rows.extend(chunk)
            if len(chunk)<100:return rows
            offset+=100

    def load(self, owner, token):
        existing=self.get(owner,token)
        if existing:return existing
        tasks=[('ingredients',None),('recipes',None),('recipe_ingredients',None),('inventory',owner),('meals',owner)]
        with ThreadPoolExecutor(5) as pool:
            futures=[pool.submit(copy_context().run,self.legacy_list,table,token,owner_id) for table,owner_id in tasks]
            values=[future.result() for future in futures]
        initial=bootstrap(*values)
        self.put(owner,token,-1,initial)
        return self.get(owner,token)

def response(document, revision):
    with measure('compute'):
        view=deepcopy(document);view.pop('requests',None)
        return present(view,revision)

def register_workspace_routes(app, legacy, identity, mode):
    repo=Repository(legacy,mode)
    app.state.workspace_repository=repo

    @app.get('/v3/workspace',tags=['통합본 v0.3'])
    def workspace(auth=Depends(identity)):
        revision,document=repo.load(*auth)
        return response(document,revision)

    def validate_apply(document, command):
        try:
            with measure('compute'):return apply(document,command.action,command.payload)
        except ValidationError as error:raise RequestValidationError(error.errors())

    def revision_conflict():
        raise HTTPException(409, '다른 작업으로 데이터가 변경되었습니다. 최신 내용을 불러와 다시 확인하세요.',
                            headers={'X-Conflict-Reason': 'revision'})

    @app.post('/v3/preview',tags=['통합본 v0.3'])
    def preview(command:Command,compact:bool=Query(False),auth=Depends(identity)):
        revision,document=repo.load(*auth)
        if revision!=command.expected_revision:revision_conflict()
        projected,summary=validate_apply(document,command)
        if not compact:return {'summary':summary,'before':response(document,revision),'after':response(projected,revision)}
        with measure('compute'):
            return {'summary':summary,'revision':revision,'before_shopping':shopping(document),'after_shopping':shopping(projected),
                    'inventory_changes':inventory_changes(document,projected)}

    @app.post('/v3/commands',tags=['통합본 v0.3'])
    def execute(command:Command,auth=Depends(identity)):
        revision,document=repo.load(*auth)
        digest=fingerprint(command.action,command.payload);request_id=str(command.request_id)
        def repeated(doc):
            found=next((r for r in doc.get('requests',[]) if r['id']==request_id),None)
            if found and found['fingerprint']!=digest:raise HTTPException(409,'같은 요청 ID에 다른 내용을 보낼 수 없습니다.')
            return found
        if repeated(document):return response(document,revision)|{'replayed':True}
        if revision!=command.expected_revision:revision_conflict()
        updated,summary=validate_apply(document,command)
        updated.setdefault('requests',[]).append({'id':request_id,'fingerprint':digest})
        updated['requests']=updated['requests'][-256:]
        result=response(updated,revision+1)|{'summary':summary,'replayed':False}
        if not repo.put(auth[0],auth[1],revision,updated):
            latest_revision,latest=repo.load(*auth)
            if repeated(latest):return response(latest,latest_revision)|{'replayed':True}
            revision_conflict()
        return result
