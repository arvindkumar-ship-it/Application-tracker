import unittest
from app.services.vault_service import numeric_values,validate_fact
from app.services.evidence_mapper import permitted_facts


class FactChecks(unittest.TestCase):
    def test_numbers_are_exact(self):
        source='Reduced latency by 20% across 3 APIs.'
        self.assertEqual([x['value'] for x in numeric_values(source)],['20%','3'])
        self.assertEqual(validate_fact({'text':source})['text'],source)
    def test_disallowed_skills_excluded(self):
        fact={'id':'1','text':'Built Python APIs.','technologies':['Python'],'is_verified_by_user':True,'superseded_by':None}
        self.assertEqual(permitted_facts([fact],[{'name':'Python','aliases':[],'claim_allowed':False}]),[])
