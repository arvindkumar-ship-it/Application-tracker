from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from sqlalchemy import select
from app.models.job import job
from app.services.text_cleaner import normalize_whitespace


def dedupe_key(company,title,location):
    return '|'.join(normalize_whitespace(x).casefold() for x in [company,title,location])


async def find_duplicate(session, company, title, location, url):
    key=dedupe_key(company,title,location)
    rows=(await session.execute(select(job))).mappings().all()
    for row in rows:
        if url and row['canonical_url']==url or company and title and row['dedupe_key']==key:
            return row['id'],'hard'
    for row in rows:
        created=row['created_at']
        if created.tzinfo is None:created=created.replace(tzinfo=timezone.utc)
        if created<datetime.now(timezone.utc)-timedelta(days=90): continue
        if SequenceMatcher(None,(company or '').casefold(),row['company_name'].casefold()).ratio()>=.9 and SequenceMatcher(None,(title or '').casefold(),row['title'].casefold()).ratio()>=.85:
            return row['id'],'possible'
    return None,None
