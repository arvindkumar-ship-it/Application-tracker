import unittest
from app.services.coverage import coverage


class CoverageChecks(unittest.TestCase):
    def test_unsupported_not_counted_and_synonyms(self):
        analysis={'must_have_keywords':[{'term':'PostgreSQL','synonyms':['Postgres']},{'term':'Kubernetes','synonyms':[]}],'nice_to_have_keywords':[],'ats_exact_phrases':[]}
        mapping={'PostgreSQL':{'supported':True,'fact_ids':['a']},'Kubernetes':{'supported':False,'fact_ids':[]}}
        sections={'section_order':['skills'],'skills':[{'name':'Postgres'},{'name':'Kubernetes'}]}
        result=coverage(analysis,mapping,sections)
        self.assertEqual(result['must_have_coverage'],.5);self.assertEqual(result['not_in_vault'][0]['term'],'Kubernetes')
    def test_no_requirements_is_unknown(self):
        self.assertIsNone(coverage({'must_have_keywords':[],'nice_to_have_keywords':[],'ats_exact_phrases':[]},{},{'section_order':[]})['must_have_coverage'])
