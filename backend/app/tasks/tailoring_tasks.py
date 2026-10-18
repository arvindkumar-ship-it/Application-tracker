import asyncio
from sqlalchemy import select,update
from app.tasks.celery_app import celery
from app.db import session_factory
from app.models import vault as v
from app.models.job import job
from app.models.tailoring import tailored_resume
from app.services.vault_service import record


async def run(row_id,render_only=False):
    from app.services.jd_analyzer import analyze
    from app.services.evidence_mapper import permitted_facts,map_keywords,contains
    from app.services.resume_assembler import rank_records,dates
    from app.services.bullet_writer import write_bullet
    from app.services.bullet_validator import validate_bullet
    from app.services.coverage import coverage
    from app.services.renderer import render
    from app.llm.client import LLMClient
    async with session_factory() as session:
        resume=await record(session,tailored_resume,row_id);options=resume['validation_report_json'].get('options',{})
        async def state(status,**values):
            report={**resume['validation_report_json'],'status':status,**values}
            await session.execute(update(tailored_resume).where(tailored_resume.c.id==resume['id']).values(validation_report_json=report));await session.commit();resume['validation_report_json']=report
        try:
            await state('processing',message='Selecting verified evidence and validating resume claims')
            j=await record(session,job,resume['job_id']);variant=await record(session,v.resume_variant,resume['base_variant_id'])
            facts=[dict(f) for f in (await session.execute(select(v.fact))).mappings()]
            skills=[dict(s) for s in (await session.execute(select(v.skill))).mappings()]
            eligible=permitted_facts(facts,skills)
            analysis=await analyze(session,j);mapping=await map_keywords(analysis,eligible,skills)
            warnings=[];dropped=[]
            if render_only:
                sections=resume['sections_json']
                for name in sections.get('section_order',[]):
                    if name in {'summary','skills'}: continue
                    for entry in sections.get(name,[]):
                        for bullet in entry['bullets']:
                            errors=validate_bullet(bullet['text'],bullet['fact_ids'],eligible)
                            if errors: raise ValueError('A cited fact changed or was superseded. Regenerate this resume before rendering.')
            else:
                profile=(await session.execute(select(v.profile))).mappings().first()
                if not profile or not profile['full_name']: raise ValueError('Save your full name in Vault → Profile first.')
                if not eligible: raise ValueError('Confirm at least one true fact in your vault before tailoring.')
                sections={'profile':{k:profile[k] for k in ['full_name','email','phone','location_city','linkedin_url','github_url','portfolio_url']},'section_order':variant['section_order'],'summary':None,'skills':[]}
                selection=[]
                for name,table,parent_type in [('experience',v.experience,'experience'),('projects',v.project,'project'),('education',v.education,'education'),('achievements',v.achievement,'achievement'),('publications',v.publication,'publication'),('certifications',v.certification,'certification')]:
                    records=[dict(r) for r in (await session.execute(select(table))).mappings()]
                    ranked=rank_records(records,[f for f in eligible if f['parent_type']==parent_type],mapping,analysis,options.get('emphasise',''))
                    limit=variant['max_projects'] if name=='projects' else 4 if name=='achievements' else len(ranked)
                    sections[name]=[]
                    for score,item,related in ranked[:limit]:
                        title=item.get('name') or item.get('role_title') or item.get('degree') or item.get('title')
                        subtitle=item.get('company') or item.get('institution') or item.get('issuer_or_event') or item.get('venue') or item.get('issuer') or item.get('role') or ''
                        bullets=[];slots=variant['max_bullets_per_project'] if name=='projects' else variant['max_bullets_per_experience'] if name=='experience' else 2
                        ordered=sorted(related,key=lambda f:(-sum(str(f['id']) in m['fact_ids'] for m in mapping.values()),str(f['id'])))
                        for fact in ordered:
                            if len(bullets)>=slots: break
                            keywords=[term for term,support in mapping.items() if str(fact['id']) in support['fact_ids'] and support['strength']=='strong']
                            bullet,errors=await write_bullet([fact],keywords)
                            if bullet:
                                bullet.update(key=f'{name}-{item["id"]}-{len(bullets)}',score=score);bullets.append(bullet)
                            else: dropped.append({'parent_id':str(item['id']),'fact_ids':[str(fact['id'])],'reasons':errors})
                        if bullets or name not in {'projects','experience'}:
                            sections[name].append({'title':title,'subtitle':subtitle,'dates':dates(item) if 'start_date' in item else item['date'].isoformat() if item.get('date') else '', 'bullets':bullets,'fact_ids':[str(f['id']) for f in related],'parent_id':str(item['id'])})
                            selection.append({'name':title,'score':score,'reason':'Verified keyword evidence, visibility priority and recency','fact_ids':[str(f['id']) for f in related]})
                    excluded=[r for r in records if not any(f['parent_id']==r['id'] for f in eligible)]
                    warnings.extend(f'{r.get("name") or r.get("role_title") or r.get("title") or r.get("institution")}: excluded because it has no eligible verified facts.' for r in excluded if name in {'projects','experience'})
                for skill in skills:
                    if not skill['claim_allowed']: continue
                    related=[str(f['id']) for f in eligible if any(contains(term,f['text']) or term.casefold() in [x.casefold() for x in f['technologies']] for term in [skill['name'],*skill['aliases']])]
                    must_match=any(any(contains(term,keyword['term']) for term in [skill['name'],*skill['aliases']]) for keyword in analysis['must_have_keywords'])
                    if related and (skill['proficiency']!='familiar' or must_match): sections['skills'].append({'name':skill['name'],'category':skill['category'],'fact_ids':related})
                sections['skills'].sort(key=lambda s:(variant['skill_group_order'].index(s['category']) if s['category'] in variant['skill_group_order'] else 99,not any(contains(s['name'],k['term']) for k in analysis['must_have_keywords']),s['name'].casefold()))
                if options.get('include_summary',True):
                    candidates=[f for f in eligible if f['parent_type'] in {'profile','education'}]
                    if candidates:
                        from app.schemas.llm_outputs import SummaryResult
                        if LLMClient().configured():
                            result=await LLMClient().complete_structured('write_summary',{'facts':[{'id':str(f['id']),'text':f['text']} for f in candidates],'supported_keywords':[k for k,m in mapping.items() if m['supported']]},SummaryResult)
                            if result.text and not validate_bullet(result.text,result.fact_ids,eligible,True): sections['summary']={'text':result.text,'fact_ids':result.fact_ids}
                        else:
                            candidate=candidates[0]
                            if not validate_bullet(candidate['text'],[str(candidate['id'])],eligible,True): sections['summary']={'text':candidate['text'],'fact_ids':[str(candidate['id'])]}
                if not any(entry.get('bullets') for name in sections['section_order'] if name not in {'summary','skills'} for entry in sections.get(name,[])):
                    raise ValueError('No verified action facts passed validation. Add specific facts beginning with Built, Developed, Designed, Analyzed or another action verb; keep each within 28 words.')
                resume['validation_report_json'].update(selection=selection,dropped_bullets=dropped,mode='llm_rewrite' if LLMClient().configured() else 'verified_extracts')
            await state('rendering',message='Rendering selectable PDF and DOCX within your page limit')
            pdf,docx,count,fit_warnings=await render(j['id'],resume['version_number'],sections,options.get('max_pages',1));warnings+=fit_warnings
            if dropped: warnings.append(f'{len(dropped)} bullets were dropped by validation.')
            report={**resume['validation_report_json'],'status':'ready','message':'Resume validated and rendered','page_count':count,'warnings':warnings}
            await session.execute(update(tailored_resume).where(tailored_resume.c.id==resume['id']).values(sections_json=sections,coverage_json=coverage(analysis,mapping,sections,warnings),validation_report_json=report,pdf_path=pdf,docx_path=docx));await session.commit()
        except Exception as e:
            await session.rollback();await state('failed',message=str(e)[:700] if isinstance(e,ValueError) else 'Resume processing failed. Check model configuration and worker logs; no unvalidated resume was finalized.')


@celery.task(name='run_tailoring')
def run_tailoring(row_id): asyncio.run(run(row_id))


@celery.task(name='render_resume')
def render_resume(row_id): asyncio.run(run(row_id,True))
