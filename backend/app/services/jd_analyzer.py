from sqlalchemy import select,insert,delete
from app.models.tailoring import jd_analysis
from app.schemas.llm_outputs import JDAnalysis
from app.llm.client import LLMClient
from app.services.evidence_verifier import verify_quote


async def analyze(session,job,refresh=False):
    existing=(await session.execute(select(jd_analysis).where(jd_analysis.c.job_id==job['id']))).mappings().first()
    if existing and not refresh: return dict(existing)
    source=job['description_full'] or ''
    client=LLMClient()
    if client.configured():
        value=(await client.complete_structured('analyze_jd',{'source_text':source},JDAnalysis)).model_dump();model=client.settings.llm_model
    else:
        value=JDAnalysis(must_have_keywords=[{'term':term,'synonyms':[],'category':'skill','jd_evidence':term} for term in job['required_skills'] if verify_quote(term,source)],nice_to_have_keywords=[{'term':term,'synonyms':[],'category':'skill','jd_evidence':term} for term in job['preferred_skills'] if verify_quote(term,source)]).model_dump();model='exact_recorded_skills'
    for key in ['must_have_keywords','nice_to_have_keywords']:
        value[key]=[item for item in value[key] if verify_quote(item['jd_evidence'],source) and verify_quote(item['term'],source)]
    value['ats_exact_phrases']=[phrase for phrase in value['ats_exact_phrases'] if verify_quote(phrase,source)]
    if existing: await session.execute(delete(jd_analysis).where(jd_analysis.c.id==existing['id']))
    row=(await session.execute(insert(jd_analysis).values(job_id=job['id'],analysis_model=model,**value).returning(jd_analysis))).mappings().one()
    await session.commit();return dict(row)
