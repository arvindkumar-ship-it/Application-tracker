import unittest
from app.services.evidence_verifier import verify_quote,verify_extraction


class EvidenceChecks(unittest.TestCase):
    def test_whitespace_and_case(self):
        self.assertTrue(verify_quote('PYTHON  APIs','Build Python\nAPIs.'))
        self.assertFalse(verify_quote('','anything'))

    def test_invented_value_with_real_quote_is_rejected(self):
        value={'company_name':{'value':'Invented Corp','evidence':'Actual Corp','confidence':'high'}}
        result,report=verify_extraction(value,'Hiring at Actual Corp')
        self.assertIsNone(result['company_name']['value'])
        self.assertIn('company_name',report['dropped_fields'])

    def test_hallucinated_email_and_deadline(self):
        result,_=verify_extraction({'apply_email':{'value':'invented@example.com','evidence':'Apply by email','confidence':'high'},'application_deadline_text':{'value':'30 Nov 2026','evidence':'30 Oct 2026','confidence':'high'}},'Apply by email. Deadline: 30 Oct 2026')
        self.assertIsNone(result['apply_email']['value']);self.assertIsNone(result['application_deadline_text']['value'])
