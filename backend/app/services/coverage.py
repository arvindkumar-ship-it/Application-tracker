from app.services.evidence_mapper import contains


def section_texts(sections):
    result={}
    for name in sections.get('section_order',[]):
        if name=='summary': result[name]=(sections.get(name) or {}).get('text','')
        elif name=='skills': result[name]=' '.join(x['name'] for x in sections.get(name,[]))
        else:
            result[name]=' '.join(' '.join([entry.get('title',''),entry.get('subtitle',''),*[b['text'] for b in entry.get('bullets',[])]]) for entry in sections.get(name,[]))
    return result


def coverage(analysis,mapping,sections,warnings=None):
    texts=section_texts(sections);covered=[];unplaced=[];unsupported=[]
    must={x['term'] for x in analysis['must_have_keywords']}
    for item in analysis['must_have_keywords']+analysis['nice_to_have_keywords']:
        term=item['term'];support=mapping.get(term,{'supported':False,'fact_ids':[]})
        locations=[name for name,text in texts.items() if support['supported'] and any(contains(t,text) for t in [term,*item.get('synonyms',[])])]
        entry={'term':term,'must_have':term in must,'fact_ids':support['fact_ids']}
        if locations: covered.append({**entry,'sections':locations})
        elif support['supported']: unplaced.append({**entry,'suggestion':'Review supporting facts and add a validated bullet if space allows.'})
        else: unsupported.append({**entry,'message':'You have no recorded experience with this. Add a fact to your vault only if it is true.'})
    total=len(must);hits=sum(x['must_have'] for x in covered)
    full=' '.join(texts.values())
    return {'must_have_coverage':hits/total if total else None,'must_have_total':total,'must_have_covered':hits,'covered_keywords':covered,'supported_but_not_placed':unplaced,'not_in_vault':unsupported,'ats_phrase_hits':[x for x in analysis['ats_exact_phrases'] if x in full],'warnings':warnings or []}
