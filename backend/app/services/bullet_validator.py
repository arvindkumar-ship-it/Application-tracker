import re

VERBS=set('built developed implemented created designed automated deployed optimized improved reduced increased analyzed evaluated integrated migrated maintained tested validated delivered led collaborated researched configured secured monitored processed trained established streamlined implemented build develop implement create design automate deploy optimize improve reduce increase analyze evaluate integrate migrate maintain test validate deliver lead collaborate research configure secure monitor process train establish streamline'.split())
FUNCTION_WORDS=set('a an the and or to of for with by in on at from into through using that which as is are was were be been being it its this these those across per via than then while within over under up out each both any all new more less had has have their them also including'.split())
BANNED=['passionate','hard-working','team player','results-driven','synergy','responsible for']


def tokens(text):
    return re.findall(r'[\w]+(?:[+#.-][\w+#]+)*',text.casefold())


def validate_bullet(text,fact_ids,facts,summary=False):
    errors=[];by_id={str(f['id']):f for f in facts};chosen=[by_id[x] for x in fact_ids if x in by_id]
    if not fact_ids or len(chosen)!=len(fact_ids) or any(not f['is_verified_by_user'] or f['superseded_by'] for f in chosen): return ['Cited facts must exist, be verified and current.']
    if len(text.split())>28: errors.append('Use at most 28 words.')
    if re.search(r'\b(i|me|my|mine|we|our|ours)\b',text,re.I): errors.append('First-person pronouns are not allowed.')
    if any(phrase in text.casefold() for phrase in BANNED): errors.append('Remove unsupported personality or filler phrases.')
    words=tokens(text)
    if not summary and (not words or words[0] not in VERBS): errors.append('Begin with a specific action verb.')
    source=' '.join(f['text'] for f in chosen)
    allowed_numbers=set(re.findall(r'\d+(?:[.,]\d+)*(?:%|\+)?',source))
    for fact in chosen:
        allowed_numbers.update(str(x['value']) for x in fact['numeric_values'])
    for number in re.findall(r'\d+(?:[.,]\d+)*(?:%|\+)?',text):
        if number not in allowed_numbers: errors.append('Number not present in cited facts: '+number)
    allowed=set(tokens(source))|FUNCTION_WORDS
    # Narrow verb equivalence permits phrasing changes without implying leadership or new outcomes.
    for group in [{'built','developed','implemented','created','build','develop','implement','create'},{'analyzed','analyze'},{'tested','test'},{'deployed','deploy'},{'designed','design'}]:
        if group & allowed: allowed|=group
    allowed.update(token for f in chosen for tech in f['technologies'] for token in tokens(tech))
    unknown=set(words)-allowed
    if unknown: errors.append('Words/claims not present in cited evidence: '+', '.join(sorted(unknown)))
    return list(dict.fromkeys(errors))
