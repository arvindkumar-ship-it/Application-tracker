import unittest
from app.services.bullet_validator import validate_bullet


class BulletChecks(unittest.TestCase):
    def setUp(self):
        self.fact={'id':'a','text':'Built Python APIs that reduced latency by 20%.','numeric_values':[{'value':'20%'}],'technologies':['Python'],'is_verified_by_user':True,'superseded_by':None}
    def test_valid(self): self.assertEqual(validate_bullet('Built Python APIs that reduced latency by 20%.',['a'],[self.fact]),[])
    def test_invalid(self):
        for text in ['Built Python APIs that reduced latency by 80%.','Built Kubernetes APIs.','I built Python APIs.','Led Python APIs.','Built passionate Python APIs.','Built '+'Python '*30]:
            with self.subTest(text=text): self.assertTrue(validate_bullet(text,['a'],[self.fact]))
    def test_unverified_and_superseded(self):
        for changes in [{'is_verified_by_user':False},{'superseded_by':'b'}]: self.assertTrue(validate_bullet('Built Python APIs.',['a'],[{**self.fact,**changes}]))
