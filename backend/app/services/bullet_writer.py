from app.llm.client import LLMClient
from app.schemas.llm_outputs import BulletResult
from app.services.bullet_validator import validate_bullet


async def write_bullet(facts,keywords):
    client=LLMClient();errors=[]
    if client.configured():
        for _ in range(3):
            result=await client.complete_structured('write_bullet',{'facts':[{'id':str(f['id']),'text':f['text']} for f in facts],'supported_keywords':keywords,'validation_errors':errors},BulletResult)
            if not result.bullet: return None,['No supported bullet returned']
            errors=validate_bullet(result.bullet,result.fact_ids,facts)
            if not errors: return {'text':result.bullet,'fact_ids':result.fact_ids},[]
        return None,errors
    for fact in facts:
        text=fact['text'].strip()
        if text.lower().startswith('i '): text=text[2:];text=text[:1].upper()+text[1:]
        errors=validate_bullet(text,[str(fact['id'])],facts)
        if not errors: return {'text':text,'fact_ids':[str(fact['id'])]},[]
    return None,errors or ['No verified action statement fits the 28-word limit.']
