import csv
import io
from fastapi import APIRouter,Depends,Body,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy import select,update,func,or_,cast,String
from app.db import get_session
from app.deps import require_auth
from app.models.job import job,master_row,status_history
from app.services.vault_service import clean,record,identifier
from app.services.job_service import get_joined,edit_master,queue_push
from app.services.normalizer import parse_date

router=APIRouter(prefix='/jobs',tags=['jobs'],dependencies=[Depends(require_auth)])


@router.get('')
async def list_jobs(search:str='',status:str='',priority:str='',company:str='',work_mode:str='',deadline_from:str='',deadline_to:str='',sort:str='created_at',descending:bool=True,page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=1000),session=Depends(get_session)):
    query=select(job.c.id).join(master_row,master_row.c.job_id==job.c.id).where(job.c.is_deleted.is_(False))
    if search:
        pattern='%'+search.replace('%','\\%').replace('_','\\_')+'%'
        query=query.where(or_(job.c.title.ilike(pattern),job.c.company_name.ilike(pattern),job.c.description_full.ilike(pattern)))
    for value,column in [(status,master_row.c.status),(priority,master_row.c.priority),(company,job.c.company_name),(work_mode,job.c.work_mode)]:
        if value: query=query.where(cast(column,String).in_(value.split(',')))
    from datetime import date
    try:
        if deadline_from: query=query.where(job.c.application_deadline>=date.fromisoformat(deadline_from))
        if deadline_to: query=query.where(job.c.application_deadline<=date.fromisoformat(deadline_to))
    except ValueError: raise HTTPException(422,'Invalid deadline range') from None
    total=(await session.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    sort_column=master_row.c[sort] if sort in {'status','priority','applied_on','follow_up_on'} else job.c[sort] if sort in job.c else job.c.created_at
    ids=(await session.execute(query.order_by((sort_column.desc() if descending else sort_column.asc()).nullslast(),job.c.id).limit(page_size).offset((page-1)*page_size))).scalars().all()
    jobs=(await session.execute(select(job).where(job.c.id.in_(ids)))).mappings().all() if ids else []
    masters=(await session.execute(select(master_row).where(master_row.c.job_id.in_(ids)))).mappings().all() if ids else []
    by_id={r['id']:dict(r) for r in jobs};by_job={r['job_id']:dict(r) for r in masters}
    counts=dict((await session.execute(select(master_row.c.status,func.count()).join(job,job.c.id==master_row.c.job_id).where(job.c.is_deleted.is_(False)).group_by(master_row.c.status))).all())
    return {'rows':[{'job':by_id[x],'master':by_job[x]} for x in ids],'total':total,'page':page,'page_size':page_size,'counts':counts}


@router.get('/export.csv')
async def export_csv(session=Depends(get_session)):
    from app.services.sheets_sync import HEADERS,row_values
    output=io.StringIO();writer=csv.writer(output);writer.writerow(HEADERS)
    for row in (await session.execute(select(job.c.id).where(job.c.is_deleted.is_(False)).order_by(job.c.created_at))).scalars():
        joined=await get_joined(session,row)
        values=row_values(joined['job'],joined['master'])
        writer.writerow(["'"+str(x) if str(x).startswith(('=','+','-','@','\t','\r')) else x for x in values])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="jobs.csv"'})


@router.get('/{row_id}')
async def detail(row_id:str,session=Depends(get_session)):
    return await get_joined(session,row_id)


@router.patch('/{row_id}')
async def edit_job(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    old=await record(session,job,row_id)
    values=clean(job,body,set(job.c.keys())-{'id','created_at','updated_at','intake_id','field_evidence','field_confidence','user_edited_fields','dedupe_key','canonical_url'})
    if any(key in values and not values[key] for key in ['title','company_name']): raise HTTPException(422,'Title and company cannot be empty')
    values['user_edited_fields']=sorted(set(old['user_edited_fields'])|set(values))
    confidence=dict(old['field_confidence']);confidence.update({k:'high' for k in body});values['field_confidence']=confidence
    if body: await session.execute(update(job).where(job.c.id==old['id']).values(**values))
    joined=await get_joined(session,row_id)
    await session.execute(update(master_row).where(master_row.c.id==joined['master']['id']).values(sheet_sync_state='pending'))
    await session.commit();queue_push(joined['master']['id']);return await get_joined(session,row_id)


@router.patch('/{row_id}/master')
async def update_master(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    return await edit_master(session,row_id,body)


@router.get('/{row_id}/history')
async def history(row_id:str,session=Depends(get_session)):
    joined=await get_joined(session,row_id)
    return (await session.execute(select(status_history).where(status_history.c.master_row_id==joined['master']['id']).order_by(status_history.c.changed_at.desc()))).mappings().all()


@router.delete('/{row_id}')
async def soft_delete(row_id:str,session=Depends(get_session)):
    joined=await get_joined(session,row_id)
    await session.execute(update(job).where(job.c.id==identifier(row_id)).values(is_deleted=True))
    notes=joined['master']['my_notes'] or ''
    if 'Deleted in app' not in notes:notes=(notes+'\nDeleted in app').strip()
    await session.execute(update(master_row).where(master_row.c.id==joined['master']['id']).values(my_notes=notes,sheet_sync_state='pending'))
    await session.commit();queue_push(joined['master']['id']);return {'ok':True,'message':'Removed from the active list. Source, history and resumes are preserved.'}
