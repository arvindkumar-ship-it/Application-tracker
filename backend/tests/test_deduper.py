import unittest
from unittest.mock import AsyncMock,MagicMock
from datetime import datetime,timezone
from app.services.deduper import dedupe_key,find_duplicate


class DedupeChecks(unittest.IsolatedAsyncioTestCase):
    async def test_hard_and_non_match(self):
        row={'id':'existing','company_name':'Fixture Co','title':'Python Developer','location_text':'Remote','canonical_url':'https://example.com/role','dedupe_key':dedupe_key('Fixture Co','Python Developer','Remote'),'created_at':datetime.now(timezone.utc)}
        result=MagicMock();result.mappings.return_value.all.return_value=[row];session=MagicMock();session.execute=AsyncMock(return_value=result)
        self.assertEqual(await find_duplicate(session,'Other','Other','','https://example.com/role'),('existing','hard'))
        self.assertEqual(await find_duplicate(session,'Fixture Co','Python Developer','Remote',None),('existing','hard'))
        self.assertEqual(await find_duplicate(session,'Different Employer','Designer','Elsewhere',None),(None,None))
