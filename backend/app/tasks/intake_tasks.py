import asyncio
import time
from sqlalchemy import update
from app.tasks.celery_app import celery
from app.db import session_factory
from app.models.intake import intake
from app.services.vault_service import record


async def process(row_id, reextract=False):
    from app.services.fetcher import fetch_url, normalize_url
    from app.services.transcriber import transcribe_files
    from app.services.extractor import extract
    from app.services.deduper import find_duplicate
    from app.config import get_settings
    started=time.monotonic()
    async with session_factory() as session:
        row=await record(session,intake,row_id)
        if row['status'] in {'approved','rejected'}: return
        async def state(status,detail,**values):
            await session.execute(update(intake).where(intake.c.id==row['id']).values(status=status,status_detail=detail,**values));await session.commit()
        step='source'
        try:
            await state('processing','Reading your source…')
            source=row['raw_text'];method=row['fetch_method'];structured=None
            if not source:
                if row['input_type']=='url': source,method,structured=await fetch_url(row['source_url'])
                elif row['input_type'] in {'screenshots','pdf'}:
                    source=await transcribe_files(row['original_files']);method='vision' if row['input_type']=='screenshots' else 'pdf_text'
            if not source or not source.strip(): raise ValueError('No readable text was found. Paste the job description below.')
            await state('processing','Extracting fields and checking source evidence…',raw_text=source,fetch_method=method)
            step='extraction'
            extraction,report,detail=await extract(source)
            if structured and not extraction.get('multiple_jobs_detected'):
                from app.services.text_cleaner import clean_html
                canonical={'title':structured.get('title'),'company_name':(structured.get('hiringOrganization') or {}).get('name') if isinstance(structured.get('hiringOrganization'),dict) else structured.get('hiringOrganization')}
                canonical['application_deadline_text']=structured.get('validThrough')
                canonical['posted_date_text']=structured.get('datePosted')
                location=structured.get('jobLocation')
                if isinstance(location,list):location=location[0] if len(location)==1 else None
                if isinstance(location,dict):
                    address=location.get('address',{})
                    if isinstance(address,dict):canonical['location_text']=address.get('addressLocality') or address.get('streetAddress')
                if structured.get('baseSalary') is not None:
                    import json
                    canonical['stipend_or_salary_text']=json.dumps(structured['baseSalary'],ensure_ascii=False)
                for key,value in canonical.items():
                    if value:
                        previous=extraction[key].get('value')
                        if previous and previous.casefold()!=str(value).casefold(): report.setdefault('jsonld_conflicts',[]).append(key)
                        extraction[key]={'value':str(value),'evidence':str(value),'confidence':'medium' if previous and previous!=value else 'high'}
            if extraction.get('multiple_jobs_detected'):
                await state('needs_manual_input','Multiple jobs detected. Keep only the job you want in the source editor, then re-extract.',extraction_json=extraction,verification_report=report);return
            value=lambda k:extraction.get(k,{}).get('value')
            duplicate,kind=await find_duplicate(session,value('company_name'),value('title'),value('location_text'),normalize_url(row['source_url']) if row['source_url'] else None)
            if kind: report['duplicate_kind']=kind
            await state('needs_review',detail,extraction_json=extraction,verification_report=report,duplicate_of_job_id=duplicate,llm_model_used=get_settings().llm_model or None,processing_ms=int((time.monotonic()-started)*1000))
        except ValueError as error:
            await state('failed' if step=='extraction' else 'needs_manual_input',str(error)[:500],processing_ms=int((time.monotonic()-started)*1000))
        except Exception:
            await session.rollback()
            await state('failed','Processing could not finish. Check API/model configuration or paste the job text and retry.',processing_ms=int((time.monotonic()-started)*1000))


@celery.task(name='process_intake')
def process_intake(row_id):
    asyncio.run(process(row_id))


@celery.task(name='re_extract')
def re_extract(row_id):
    asyncio.run(process(row_id,True))
