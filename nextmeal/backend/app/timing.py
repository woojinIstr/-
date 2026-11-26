"""Request-local performance measurements; never log credentials or payloads."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import logging
from time import perf_counter
from uuid import uuid4

current_metrics = ContextVar('nextmeal_metrics', default=None)
logger = logging.getLogger('uvicorn.error')

def note_auth(method):
    metrics=current_metrics.get()
    if metrics is not None:metrics['auth_method']=method

@contextmanager
def measure(stage, upstream=False):
    start=perf_counter()
    try:yield
    finally:
        metrics=current_metrics.get()
        if metrics is not None:metrics['events'].append((stage,(perf_counter()-start)*1000,upstream))

def install_timing(app):
    @app.middleware('http')
    async def timing(request, call_next):
        metrics={'events':[]};token=current_metrics.set(metrics);start=perf_counter();response=None
        request_id=str(uuid4())
        try:
            response=await call_next(request)
            total=(perf_counter()-start)*1000
            durations={stage:sum(ms for name,ms,_ in metrics['events'] if name==stage) for stage in ['auth','db_read','db_write','compute']}
            response.headers['Server-Timing']=', '.join(f'{name};dur={ms:.2f}' for name,ms in (durations|{'total':total}).items())
            response.headers['X-Request-ID']=request_id
            response.headers['X-Upstream-Requests']=str(sum(int(remote) for _,_,remote in metrics['events']))
            if metrics.get('auth_method'):response.headers['X-Auth-Verification']=metrics['auth_method']
            return response
        finally:
            if request.url.path.startswith('/v3/'):
                route=getattr(request.scope.get('route'),'path','/v3/unknown')
                record={'request_id':request_id,'method':request.method,'route':route,'status':response.status_code if response is not None else 500,'total_ms':round((perf_counter()-start)*1000,2),'upstream_requests':sum(int(remote) for _,_,remote in metrics['events'])}
                record['auth_method']=metrics.get('auth_method','none')
                for stage in ['auth','db_read','db_write','compute']:record[stage+'_ms']=round(sum(ms for name,ms,_ in metrics['events'] if name==stage),2)
                logger.info('nextmeal_timing %s',json.dumps(record,separators=(',',':')))
            current_metrics.reset(token)
