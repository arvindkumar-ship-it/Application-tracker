from datetime import date


def rank_records(records,facts,mapping,analysis,emphasise=''):
    result=[]
    must={x['term'] for x in analysis['must_have_keywords']}
    for record in records:
        related=[f for f in facts if f['parent_id']==record['id']]
        if not related: continue
        ids={str(f['id']) for f in related}
        score=sum((3 if term in must else 1)*(1 if evidence['strength']=='strong' else .5) for term,evidence in mapping.items() if ids.intersection(evidence['fact_ids']))
        score+=.5*(record.get('visibility_priority') or 0)
        if emphasise:
            from app.services.evidence_mapper import contains
            score+=sum(.25 for word in emphasise.split() if any(contains(word,f['text']) for f in related))
        recent=record.get('end_date') or record.get('start_date')
        score+=max(0,1-(date.today()-recent).days/3650) if recent else 0
        result.append((score,record,related))
    return sorted(result,key=lambda x:(-x[0],-(x[1].get('end_date') or x[1].get('start_date') or date.min).toordinal(),x[1].get('sort_order',0),str(x[1]['id'])))


def dates(record):
    start=record.get('start_date');end=record.get('end_date')
    if not start: return ''
    return start.strftime('%b %Y')+' – '+(end.strftime('%b %Y') if end else 'Present')
