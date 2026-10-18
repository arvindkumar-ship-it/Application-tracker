import json
import re
from pathlib import Path
from fastapi import APIRouter,Depends,Body,HTTPException
from sqlalchemy import select,insert,update
from app.db import get_session
from app.deps import require_auth
from app.config import get_settings
from app.models.sync import app_setting,sheet_sync_log
from app.models.job import master_row
from app.services.vault_service import record
from app.services import sheets_sync as svc

router=APIRouter(prefix='/sheets',tags=['sheets'],dependencies=[Depends(require_auth)])


@router.get('/settings')
async def settings(session=Depends(get_session)):
    config=await svc.settings(session);runtime=get_settings()
    config.update(llm_model=runtime.llm_model,llm_configured=bool(runtime.llm_model and runtime.anthropic_api_key),service_account_mounted=Path(runtime.google_service_account_json_path).is_file(),service_account_path=runtime.google_service_account_json_path)
    config['sync_counts']=dict((await session.execute(select(master_row.c.sheet_sync_state,__import__('sqlalchemy').func.count()).group_by(master_row.c.sheet_sync_state))).all())
    return config


@router.put('/settings')
async def save_settings(body:dict=Body(...),session=Depends(get_session)):
    for key in body:
        if key not in {'google_sheet_id','google_sheet_tab_name'}: raise HTTPException(422,'Unknown setting; secrets must stay in the local environment')
    for key,value in body.items():
        if not isinstance(value,str): raise HTTPException(422,'Settings must be text')
        value=value.strip()
        if key=='google_sheet_id' and value and not re.fullmatch(r'[A-Za-z0-9_-]{10,200}',value): raise HTTPException(422,'Enter the Sheet ID, not its complete URL')
        if key=='google_sheet_tab_name' and (not value or len(value)>100): raise HTTPException(422,'Enter a tab name up to 100 characters')
        row=(await session.execute(select(app_setting.c.id).where(app_setting.c.key==key))).first()
        if row: await session.execute(update(app_setting).where(app_setting.c.key==key).values(value=value))
        else: await session.execute(insert(app_setting).values(key=key,value=value))
    await session.commit();return await settings(session)


@router.post('/test')
async def test_connection(session=Depends(get_session)):
    try: return await svc.Sheets(await svc.settings(session)).setup()
    except ValueError as e: raise HTTPException(422,str(e)) from None


@router.post('/push-all')
async def push_all(session=Depends(get_session)):
    config=await svc.settings(session)
    if not config.get('google_sheet_id'): raise HTTPException(422,'Configure your Google Sheet first')
    await session.execute(update(master_row).where(master_row.c.sheet_sync_state!='conflict').values(sheet_sync_state='pending'));await session.commit()
    from app.tasks.sheet_tasks import push_pending
    try: push_pending.delay()
    except Exception: raise HTTPException(503,'Worker queue unavailable. Rows remain pending and safe.') from None
    return {'message':'Push queued. Conflicted rows are preserved until you resolve them.'}


@router.post('/pull')
async def pull(session=Depends(get_session)):
    try: return await svc.pull(session)
    except ValueError as e: raise HTTPException(422,str(e)) from None


@router.get('/conflicts')
async def conflicts(session=Depends(get_session)):
    result=[]
    for row in (await session.execute(select(master_row).where(master_row.c.sheet_sync_state=='conflict'))).mappings():
        entry=(await session.execute(select(sheet_sync_log).where(sheet_sync_log.c.master_row_id==row['id'],sheet_sync_log.c.action=='conflict').order_by(sheet_sync_log.c.created_at.desc()).limit(1))).mappings().first()
        if entry:
            try: detail=json.loads(entry['detail'])
            except ValueError: detail={}
            result.append({'master_row_id':row['id'],'job_id':row['job_id'],**detail})
    return result


@router.post('/conflicts/{row_id}/resolve')
async def resolve(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    row=await record(session,master_row,row_id,lock=True)
    if row['sheet_sync_state']!='conflict': raise HTTPException(409,'This row no longer has a conflict')
    if body.get('choice') not in {'app','sheet'}: raise HTTPException(422,'Choose app or sheet')
    entry=(await session.execute(select(sheet_sync_log).where(sheet_sync_log.c.master_row_id==row['id'],sheet_sync_log.c.action=='conflict').order_by(sheet_sync_log.c.created_at.desc()).limit(1))).mappings().first()
    if not entry: raise HTTPException(409,'Conflict evidence unavailable; pull again')
    detail=json.loads(entry['detail']);sheet=detail['sheet']
    if body['choice']=='sheet':
        try: await svc.apply_sheet_changes(session,row,sheet)
        except ValueError as e: raise HTTPException(422,str(e)) from None
    await session.execute(update(master_row).where(master_row.c.id==row['id']).values(last_pushed_snapshot=sheet,sheet_sync_state='pending'))
    await svc.log(session,'pull',row['id'],'update','Conflict resolved explicitly: keep '+body['choice'])
    await session.commit()
    from app.services.job_service import queue_push
    queue_push(row['id']);return {'ok':True}
