import unittest
from app.services.normalizer import compensation,parse_date,experience


class NormalizerChecks(unittest.TestCase):
    def test_compensation(self):
        cases=[('₹15,000–20,000/month',15000,20000,'INR','month'),('INR 3-5 LPA',300000,500000,'INR','year'),('Unpaid',0,None,None,'unspecified'),('$20/hr',20,None,'USD','hour'),('Performance based',None,None,None,'unspecified'),('INR 25000 per month',25000,None,'INR','month'),('USD 90000/year',90000,None,'USD','year'),('€25/hour',25,None,'EUR','hour'),('Salary negotiable',None,None,None,'unspecified'),('',None,None,None,'unspecified')]
        for text,low,high,currency,period in cases:
            with self.subTest(text=text): self.assertEqual(compensation(text),{'comp_min':low,'comp_max':high,'comp_currency':currency,'comp_period':period})
    def test_dates(self):
        for source,expected in [('Apply by 30th Oct 2026','2026-10-30'),('2026-12-31','2026-12-31'),('30/10/2026','2026-10-30'),('October 30, 2026','2026-10-30'),('2026-01-01','2026-01-01'),('within 7 days',None),('Oct 2026',None),('ASAP',None),('',None),('2026',None)]:
            with self.subTest(source=source): self.assertEqual(str(parse_date(source)) if parse_date(source) else None,expected)
    def test_experience(self):
        for source,low,high in [('freshers',0,None),('2+ years',2,None),('0-2 years',0,2),('3-5 yrs',3,5),('',None,None),('not mentioned',None,None)]:
            with self.subTest(source=source): self.assertEqual(experience(source),{'experience_min_years':low,'experience_max_years':high})
