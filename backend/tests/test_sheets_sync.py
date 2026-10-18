import unittest
from app.services.sheets_sync import compare,validate_editable,HEADERS


class SyncChecks(unittest.TestCase):
    def test_exact_header_count(self): self.assertEqual(len(HEADERS),33)
    def test_three_way(self):
        baseline={'status':'to_apply'}
        self.assertEqual(compare({'status':'applied'},{'status':'to_apply'},baseline)[0],{'status':'applied'})
        self.assertEqual(compare({'status':'to_apply'},{'status':'interviewing'},baseline),({},{}))
        self.assertIn('status',compare({'status':'applied'},{'status':'interviewing'},baseline)[1])
    def test_invalid_status_and_dates(self):
        for values in [{'status':'nonsense'},{'priority':'urgent'},{'applied_on':'tomorrow'}]:
            with self.subTest(values=values),self.assertRaises(ValueError):validate_editable(values)
