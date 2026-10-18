import uuid
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Form,UploadFile,File,Body
from sqlalchemy import select,insert,update
from PIL import Image
import io
import pymupdf as fitz
from app.db import get_session
from app.deps import require_auth
from app.config import get_settings
from app.models.intake import intake
from app.services.vault_service import record
from app.schemas.llm_outputs import SCALAR_FIELDS,LIST_FIELDS

router=APIRouter(prefix='/intake',tags=['intake'],dependencies=[Depends(require_auth)])


def enqueue(row_id,reextract=False):
    from app.tasks.intake_tasks import process_intake,re_extract
    try: (re_extract if reextract else process_intake).delay(str(row_id))
    except Exception: pass  # The persisted intake remains queued; Redis health exposes the outage.


@router.get('')
async def list_intakes(status:str|None=None,session=Depends(get_session)):
    query=select(intake).order_by(intake.c.created_at.desc()).limit(200)
    if status: query=query.where(intake.c.status==status)
    return (await session.execute(query)).mappings().all()


@router.post('')
async def create_intake(input_type:str=Form(...),url:str|None=Form(None),text:str|None=Form(None),files:list[UploadFile]=File(default=[]),session=Depends(get_session)):
    if input_type not in {'url','text','screenshots','pdf'}: raise HTTPException(422,'Choose link, text, screenshots or PDF')
    if input_type=='url':
        from app.services.fetcher import safe_target
        try: await safe_target(url or '')
        except ValueError as e: raise HTTPException(422,str(e)) from None
    if input_type=='text' and not (text or '').strip(): raise HTTPException(422,'Paste the job description')
    if len(text or '')>250_000: raise HTTPException(422,'Job text is too long')
    if len(files)>12: raise HTTPException(422,'Upload at most 12 files')
    if input_type in {'screenshots','pdf'} and not files: raise HTTPException(422,'Choose at least one file')
    row_id=uuid.uuid4();stored=[]
    try:
        for uploaded in files:
            data=await uploaded.read(10*1024*1024+1)
            if len(data)>10*1024*1024: raise HTTPException(422,'Each upload must be 10 MB or smaller')
            try:
                if data.startswith(b'%PDF-'):
                    document=fitz.open(stream=data,filetype='pdf')
                    if document.is_encrypted or document.page_count>30: raise ValueError()
                    document.close();suffix='.pdf'
                    if input_type=='screenshots': raise ValueError()
                else:
                    with Image.open(io.BytesIO(data)) as image:
                        if image.format not in {'PNG','JPEG','WEBP'} or image.width*image.height>40_000_000: raise ValueError()
                        suffix={'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[image.format];image.verify()
                    if input_type=='pdf': raise ValueError()
            except Exception: raise HTTPException(422,'Upload valid PNG, JPG, WEBP screenshots or a readable PDF matching the selected mode') from None
            directory=Path(get_settings().data_dir)/'uploads'/str(row_id);directory.mkdir(parents=True,exist_ok=True)
            path=directory/(str(uuid.uuid4())+suffix);path.write_bytes(data);stored.append(str(path))
        await session.execute(insert(intake).values(id=row_id,input_type=input_type,source_url=url if input_type=='url' else None,raw_text=text if input_type=='text' else None,original_files=stored,status='queued',status_detail='Waiting for the background worker',fetch_method='pasted' if input_type=='text' else 'none'))
        await session.commit()
    except Exception:
        for path in stored: Path(path).unlink(missing_ok=True)
        raise
    enqueue(row_id)
    return {'intake_id':row_id}


@router.get('/{row_id}')
async def get_intake(row_id:str,session=Depends(get_session)):
    return await record(session,intake,row_id)


@router.patch('/{row_id}/raw-text')
async def edit_source(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    row=await record(session,intake,row_id,lock=True)
    if row['status'] in {'approved','rejected','processing'}: raise HTTPException(409,'Source cannot be edited in the current state')
    text=body.get('raw_text')
    if not isinstance(text,str) or not text.strip() or len(text)>250_000: raise HTTPException(422,'Enter source text up to 250,000 characters')
    await session.execute(update(intake).where(intake.c.id==row['id']).values(raw_text=text,status='needs_manual_input',extraction_json={},verification_report={},duplicate_of_job_id=None,status_detail='Source changed. Re-extract before approving.'))
    await session.commit();return {'ok':True}


@router.post('/{row_id}/re-extract')
async def reextract(row_id:str,session=Depends(get_session)):
    row=await record(session,intake,row_id,lock=True)
    if row['status'] in {'approved','rejected','processing'}: raise HTTPException(409,'Cannot re-extract this intake in its current state')
    await session.execute(update(intake).where(intake.c.id==row['id']).values(status='queued',status_detail='Queued for extraction'))
    await session.commit();enqueue(row_id,True);return {'ok':True}


@router.put('/{row_id}/fields')
async def edit_fields(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    row=await record(session,intake,row_id,lock=True)
    if row['status']!='needs_review': raise HTTPException(409,'Wait for extraction to finish before editing')
    if set(body)-set(SCALAR_FIELDS+LIST_FIELDS): raise HTTPException(422,'Unknown extraction field')
    extraction=dict(row['extraction_json']);report=dict(row['verification_report']);edited=set(report.get('edited_fields',[]))
    for key,value in body.items():
        if key in LIST_FIELDS:
            if not isinstance(value,list) or any(not isinstance(x,str) for x in value): raise HTTPException(422,'List fields require text items')
            extraction[key]=[{'value':x,'evidence':None,'confidence':'high'} for x in value if x.strip()]
        else:
            if value is not None and not isinstance(value,str): raise HTTPException(422,'Fields require text or null')
            extraction[key]={'value':value or None,'evidence':None,'confidence':'high'}
        edited.add(key)
    report['edited_fields']=sorted(edited)
    await session.execute(update(intake).where(intake.c.id==row['id']).values(extraction_json=extraction,verification_report=report));await session.commit()
    return await record(session,intake,row_id)


@router.post('/{row_id}/approve')
async def approve(row_id:str,body:dict=Body(default={}),session=Depends(get_session)):
    from app.services.job_service import approve_intake
    return await approve_intake(session,row_id,bool(body.get('force_duplicate')))


@router.post('/{row_id}/reject')
async def reject(row_id:str,session=Depends(get_session)):
    row=await record(session,intake,row_id,lock=True)
    if row['status']=='approved': raise HTTPException(409,'Already approved')
    await session.execute(update(intake).where(intake.c.id==row['id']).values(status='rejected',status_detail='Discarded by you'));await session.commit();return {'ok':True}
