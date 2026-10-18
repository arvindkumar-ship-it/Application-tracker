import re
from app.llm.client import LLMClient
from app.schemas.llm_outputs import EvidenceJudgement


def contains(term,text):
    return bool(term) and bool(re.search(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text,re.I))


def permitted_facts(facts,skills):
    blocked=[alias for skill in skills if not skill['claim_allowed'] for alias in [skill['name'],*skill['aliases']]]
    return [f for f in facts if f['is_verified_by_user'] and not f['superseded_by'] and not any(contains(term,f['text']) or term.casefold() in [x.casefold() for x in f['technologies']] for term in blocked)]


async def map_keywords(analysis,facts,skills):
    mapping={};client=LLMClient()
    for keyword in analysis['must_have_keywords']+analysis['nice_to_have_keywords']:
        terms=[keyword['term'],*keyword.get('synonyms',[])]
        for skill in skills:
            if skill['claim_allowed'] and any(contains(t,' '.join([skill['name'],*skill['aliases']])) for t in terms): terms.extend([skill['name'],*skill['aliases']])
        supported=[str(f['id']) for f in facts if any(contains(term,f['text']) or any(term.casefold()==t.casefold() for t in f['technologies']) for term in terms)]
        strength='strong'
        if not supported and client.configured() and facts:
            judged=await client.complete_structured('map_evidence',{'keyword':keyword['term'],'facts':[{'id':str(f['id']),'text':f['text']} for f in facts]},EvidenceJudgement)
            # Semantic suggestions are shown as partial, not automatically used to insert new terms.
            supported=[x for x in judged.fact_ids if x in {str(f['id']) for f in facts}];strength='partial'
        mapping[keyword['term']]={'fact_ids':supported,'strength':strength,'supported':bool(supported)}
    return mapping
