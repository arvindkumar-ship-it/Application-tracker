"""Opt-in external-model coverage; skipped when the key/model are unavailable."""
import json
import unittest
from pathlib import Path
from app.config import get_settings
from app.services.extractor import extract
from app.services.text_cleaner import clean_html
from app.services.transcriber import transcribe_files


class GoldenChecks(unittest.IsolatedAsyncioTestCase):
    async def test_twelve_source_fixtures(self):
        config=get_settings()
        if not config.anthropic_api_key or not config.llm_model:self.skipTest('Anthropic key/model required; no external extraction accuracy claim is made without this run')
        root=Path(__file__).parent/'fixtures'
        expected=sorted(root.glob('expected_*.json'));self.assertEqual(len(expected),12)
        for filename in expected:
            fixture=json.loads(filename.read_text());path=root/fixture['file']
            with self.subTest(file=path.name):
                source=await transcribe_files([str(path)]) if path.suffix in {'.png','.pdf'} else clean_html(path.read_text()) if path.suffix=='.html' else path.read_text()
                result,report,_=await extract(source)
                if fixture['multiple_jobs']:
                    self.assertTrue(result['multiple_jobs_detected']);continue
                self.assertFalse(report['dropped_fields'])
                self.assertEqual(result['title']['value'],fixture['title'])
                self.assertEqual(result['company_name']['value'],fixture['company_name'])
                if fixture['deadline_absent']:self.assertIsNone(result['application_deadline_text']['value'])
