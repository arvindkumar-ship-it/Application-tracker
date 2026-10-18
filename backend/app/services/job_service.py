import csv
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select,insert,update
from app.models.job import job,master_row,status_history
from app.models.intake import intake
from app.services.vault_service import record,clean
from app.services.normalizer import compensation,experience,parse_date
from app.services.deduper import dedupe_key

EDITABLE={'status','priority','applied_on','follow_up_on','my_notes','interview_notes'}


def queue_push(row_id):
    try:
        from app.tasks.sheet_tasks import push_row_to_sheet
        push_row_to_sheet.delay(str(row_id))
    except Exception: pass


async def approve_intake(session,row_id,force_duplicate=False):
    source=await record(session,intake,row_id,lock=True)
    if source['status']=='approved':
        existing=(await session.execute(select(job.c.id).where(job.c.intake_id==source['id']))).scalar_one()
        return {'job_id':existing}
    if source['status']!='needs_review': raise HTTPException(409,'This intake is not ready for approval')
    if source['duplicate_of_job_id'] and not force_duplicate: raise HTTPException(409,'Choose Add anyway or discard this duplicate')
    extracted=source['extraction_json'];values={};evidence={};confidence={}
    for key,item in extracted.items():
        if key in {'multiple_jobs_detected','titles'}: continue
        value=[x['value'] for x in item if x.get('value')] if isinstance(item,list) else item.get('value')
        mapped={'description_summary_verbatim':'description_full','application_deadline_text':'application_deadline','posted_date_text':'posted_date'}.get(key,key)
        if mapped in job.c:
            if mapped in {'application_deadline','posted_date'}: value=parse_date(value)
            if value is not None: values[mapped]=value
        evidence[mapped]=[x.get('evidence') for x in item] if isinstance(item,list) else item.get('evidence')
        confidence[mapped]='high' if isinstance(item,list) else item.get('confidence','low')
    if not values.get('title') or not values.get('company_name'): raise HTTPException(422,'Title and company name are required before approval')
    for key,choices in [('work_mode',{'onsite','hybrid','remote'}),('employment_type',{'internship','full_time','part_time','contract','freelance'})]:
        values[key]=values.get(key,'unspecified').lower().replace(' ','_').replace('-','_')
        if values[key] not in choices: values[key]='unspecified'
    from app.services.fetcher import normalize_url
    values.update(compensation(values.get('stipend_or_salary_text')));values.update(experience(values.get('experience_required_text')))
    values.update(intake_id=source['id'],source_url=source['source_url'],description_full=source['raw_text'],canonical_url=normalize_url(source['source_url']) if source['source_url'] else None,field_evidence=evidence,field_confidence=confidence,user_edited_fields=source['verification_report'].get('edited_fields',[]))
    values['dedupe_key']=dedupe_key(values['company_name'],values['title'],values.get('location_text'))
    row=(await session.execute(insert(job).values(**values).returning(job))).mappings().one()
    master=(await session.execute(insert(master_row).values(job_id=row['id'],status='to_apply',priority='medium',sheet_sync_state='pending').returning(master_row))).mappings().one()
    await session.execute(update(intake).where(intake.c.id==source['id']).values(status='approved',status_detail='Added to your master list'))
    await session.commit();queue_push(master['id']);return {'job_id':row['id']}


async def get_joined(session,job_id):
    j=await record(session,job,job_id)
    m=(await session.execute(select(master_row).where(master_row.c.job_id==j['id']))).mappings().first()
    if not m: raise HTTPException(404,'Master row not found')
    return {'job':j,'master':dict(m)}


async def edit_master(session,job_id,body,via='app'):
    joined=await get_joined(session,job_id);old=await record(session,master_row,joined['master']['id'],lock=True)
    values=clean(master_row,body,EDITABLE)
    if values.get('status')=='applied' and old['applied_on'] is None and not values.get('applied_on'): values['applied_on']=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if 'status' in values and values['status']!=old['status']:
        await session.execute(insert(status_history).values(master_row_id=old['id'],from_status=old['status'],to_status=values['status'],changed_via=via))
    if values:
        await session.execute(update(master_row).where(master_row.c.id==old['id']).values(**values,sheet_sync_state='pending'))
    await session.commit();queue_push(old['id']);return await get_joined(session,job_id)
