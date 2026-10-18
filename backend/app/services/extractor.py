from app.llm.client import LLMClient
from app.schemas.llm_outputs import JobExtraction
from app.services.evidence_verifier import verify_extraction


async def extract(source):
    client=LLMClient()
    if not client.configured():
        empty=JobExtraction().model_dump()
        import re
        titles=re.findall(r'^\s*(?:role|job title|position|second job)\s*:\s*(.+)$',source,re.I|re.M)
        if len(titles)>1:
            empty.update(multiple_jobs_detected=True,titles=titles)
            return empty,{'manual_review':True,'dropped_fields':[],'fields':{}},'Multiple jobs detected. Keep only one job in the source editor.'
        labels={'title':['title','role','job title','position'],'company_name':['company','company name'],'location_text':['location'],'stipend_or_salary_text':['salary','stipend','compensation'],'experience_required_text':['experience','experience required'],'application_deadline_text':['deadline','apply by'],'required_skills':['required skills','must have'],'preferred_skills':['preferred skills','nice to have'],'responsibilities':['responsibilities'],'qualifications':['qualifications'],'apply_email':['apply email'],'apply_url':['apply link','apply url']}
        for key,names in labels.items():
            for name in names:
                match=re.search(r'^\s*'+re.escape(name)+r'\s*:\s*(.+)$',source,re.I|re.M)
                if not match: continue
                value=match.group(1).strip();evidence=match.group(0).strip()
                if isinstance(empty[key],list): empty[key]=[{'value':x.strip(),'evidence':evidence,'confidence':'medium'} for x in re.split(r'[,;]',value) if x.strip()]
                else: empty[key]={'value':value,'evidence':evidence,'confidence':'medium'}
                break
        empty,report=verify_extraction(empty,source)
        report.update(manual_review=True,method='exact_labelled_fields')
        return empty, report, 'Exact labelled fields were copied without an LLM. Review the source and fill any unknowns. Automatic reading of unlabelled content needs Anthropic configuration.'
    result=await client.complete_structured('extract_job',{'source_text':source},JobExtraction)
    values,report=verify_extraction(result.model_dump(),source)
    return values,report,'Review extracted fields against their source before approving.'
