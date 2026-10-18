from pathlib import Path
from fastapi import APIRouter,Depends,Body,HTTPException
from fastapi.responses import FileResponse,Response
from sqlalchemy import select,insert,update,func
from pydantic import BaseModel,Field
from app.db import get_session
from app.deps import require_auth
from app.models import vault as v
from app.models.job import job,master_row
from app.models.tailoring import tailored_resume
from app.services.vault_service import record,seed_variants,identifier
from app.services.evidence_mapper import permitted_facts
from app.config import get_settings

router=APIRouter(tags=['tailoring'],dependencies=[Depends(require_auth)])


class Options(BaseModel):
    base_variant_id:str|None=None
    max_pages:int=Field(default=1,ge=1,le=2)
    include_summary:bool=True
    emphasise:str=Field(default='',max_length=500)


@router.post('/jobs/{job_id}/jd-analysis')
async def analysis(job_id:str,refresh:bool=False,session=Depends(get_session)):
    from app.services.jd_analyzer import analyze
    row=await record(session,job,job_id,lock=True)
    return await analyze(session,row,refresh)


@router.post('/jobs/{job_id}/tailor')
async def tailor(job_id:str,body:Options,session=Depends(get_session)):
    await record(session,job,job_id,lock=True);await seed_variants(session)
    profile=(await session.execute(select(v.profile))).mappings().first()
    if not profile or not profile['full_name']: raise HTTPException(422,'Save your full name in Vault → Profile first')
    facts=(await session.execute(select(v.fact))).mappings().all();skills=(await session.execute(select(v.skill))).mappings().all()
    if not permitted_facts(facts,skills): raise HTTPException(422,'Confirm at least one fact in your vault before tailoring')
    variant=await record(session,v.resume_variant,body.base_variant_id) if body.base_variant_id else (await session.execute(select(v.resume_variant).order_by(v.resume_variant.c.is_default.desc(),v.resume_variant.c.created_at))).mappings().first()
    number=(await session.execute(select(func.max(tailored_resume.c.version_number)).where(tailored_resume.c.job_id==identifier(job_id)))).scalar_one() or 0
    row=(await session.execute(insert(tailored_resume).values(job_id=identifier(job_id),base_variant_id=variant['id'],version_number=number+1,validation_report_json={'status':'queued','options':body.model_dump(),'message':'Waiting for the resume worker'}).returning(tailored_resume))).mappings().one()
    await session.commit()
    from app.tasks.tailoring_tasks import run_tailoring
    try: run_tailoring.delay(str(row['id']))
    except Exception: raise HTTPException(503,'Resume saved as queued, but the worker queue is unavailable') from None
    return {'tailored_resume_id':row['id']}


@router.get('/jobs/{job_id}/tailored')
async def versions(job_id:str,session=Depends(get_session)):
    await record(session,job,job_id)
    rows=(await session.execute(select(tailored_resume).where(tailored_resume.c.job_id==identifier(job_id)).order_by(tailored_resume.c.version_number.desc()))).mappings().all()
    return [{k:r[k] for k in ['id','version_number','is_final','pdf_path','created_at','validation_report_json']} for r in rows]


@router.get('/tailored/{row_id}')
async def resume(row_id:str,session=Depends(get_session)):
    row=await record(session,tailored_resume,row_id)
    return {**row,'status':row['validation_report_json'].get('status','unknown')}


@router.patch('/tailored/{row_id}/bullet')
async def edit_bullet(row_id:str,body:dict=Body(...),session=Depends(get_session)):
    from app.services.bullet_validator import validate_bullet
    row=await record(session,tailored_resume,row_id,lock=True)
    if row['is_final']: raise HTTPException(409,'Generate a new version to edit; the final version remains reproducible')
    if row['validation_report_json'].get('status') not in {'ready','needs_render'}: raise HTTPException(409,'Wait for processing before editing')
    if not isinstance(body.get('new_text'),str): raise HTTPException(422,'Enter bullet text')
    facts=(await session.execute(select(v.fact))).mappings().all();skills=(await session.execute(select(v.skill))).mappings().all();eligible=permitted_facts(facts,skills)
    sections=dict(row['sections_json']);found=False
    for name in sections['section_order']:
        if name in {'summary','skills'}: continue
        for entry in sections.get(name,[]):
            for bullet in entry['bullets']:
                if bullet['key']==body.get('bullet_key'):
                    errors=validate_bullet(body['new_text'],bullet['fact_ids'],eligible)
                    if errors: raise HTTPException(422,' '.join(errors))
                    bullet['text']=body['new_text'];found=True
    if not found: raise HTTPException(404,'Bullet not found')
    report={**row['validation_report_json'],'status':'needs_render','message':'Bullet validated. Re-render to update downloads and coverage.'}
    await session.execute(update(tailored_resume).where(tailored_resume.c.id==row['id']).values(sections_json=sections,validation_report_json=report,pdf_path=None,docx_path=None));await session.commit();return {'ok':True,'message':report['message']}


@router.post('/tailored/{row_id}/render')
async def render(row_id:str,session=Depends(get_session)):
    row=await record(session,tailored_resume,row_id,lock=True)
    if row['validation_report_json'].get('status') not in {'ready','needs_render','failed'} or not row['sections_json']: raise HTTPException(409,'No validated content is ready to render')
    if row['is_final']: raise HTTPException(409,'Final resumes cannot be overwritten')
    await session.execute(update(tailored_resume).where(tailored_resume.c.id==row['id']).values(validation_report_json={**row['validation_report_json'],'status':'queued'}));await session.commit()
    from app.tasks.tailoring_tasks import render_resume
    render_resume.delay(str(row['id']));return {'ok':True}


@router.post('/tailored/{row_id}/mark-final')
async def mark_final(row_id:str,session=Depends(get_session)):
    row=await record(session,tailored_resume,row_id)
    await record(session,job,row['job_id'],lock=True)
    if row['validation_report_json'].get('status')!='ready' or not row['pdf_path'] or not Path(row['pdf_path']).is_file(): raise HTTPException(409,'Wait for a validated, rendered resume before marking it final')
    await session.execute(update(tailored_resume).where(tailored_resume.c.job_id==row['job_id']).values(is_final=False))
    await session.execute(update(tailored_resume).where(tailored_resume.c.id==row['id']).values(is_final=True))
    await session.execute(update(master_row).where(master_row.c.job_id==row['job_id']).values(resume_version_id=row['id'],sheet_sync_state='pending'));await session.commit()
    master=(await session.execute(select(master_row.c.id).where(master_row.c.job_id==row['job_id']))).scalar_one()
    from app.services.job_service import queue_push
    queue_push(master);return {'ok':True}


@router.get('/tailored/{row_id}/{extension}')
async def download(row_id:str,extension:str,download:bool=False,page:int=1,session=Depends(get_session)):
    if extension not in {'pdf','docx','preview'}: raise HTTPException(404,'File type not found')
    row=await record(session,tailored_resume,row_id);name=row[('pdf' if extension=='preview' else extension)+'_path']
    if row['validation_report_json'].get('status')!='ready' or not name: raise HTTPException(409,'Resume file is not ready; render the validated content first')
    path=Path(name).resolve();root=(Path(get_settings().data_dir)/'resumes').resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404,'Resume file unavailable')
    if extension=='preview':
        import pymupdf
        with pymupdf.open(path) as document:
            if not 1<=page<=document.page_count: raise HTTPException(422,'Page number is outside this resume')
            image=document[page-1].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).tobytes('png')
        return Response(image,media_type='image/png')
    return FileResponse(path,filename=f'v{row["version_number"]}.{extension}',content_disposition_type='inline' if extension=='pdf' and not download else 'attachment',media_type='application/pdf' if extension=='pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
