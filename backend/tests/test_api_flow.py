"""Phase 1 checks only. Live Docker/database and later-phase flows remain gated."""
import os
import secrets
import unittest
from unittest.mock import patch
from app.security import hash_password, verify_password, create_session, verify_session, valid_password_hash

PASSWORD = secrets.token_urlsafe(24)
ENCODED = hash_password(PASSWORD)
# Test process only; never reuse these credentials in a running portal.
os.environ.update(DATABASE_URL="postgresql+asyncpg://portal:portal@localhost:5432/portal", REDIS_URL="redis://localhost:6379/0", SESSION_SECRET=secrets.token_urlsafe(40), APP_PASSWORD_HASH=ENCODED)
from fastapi.testclient import TestClient
from app.main import app
from app.models import metadata


class FakeRedis:
    def __init__(self): self.failures = 0
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return None
    async def get(self, key): return str(self.failures)
    async def eval(self, *args): self.failures += 1
    async def delete(self, key): self.failures = 0


class FoundationChecks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_all_tables_registered(self):
        self.assertEqual(set(metadata.tables), {"profile", "education", "experience", "project", "project_tech", "achievement", "publication", "certification", "skill", "resume_variant", "fact", "intake", "job", "master_row", "status_history", "jd_analysis", "tailored_resume", "sheet_sync_log", "app_setting"})

    def test_password_and_signed_session(self):
        self.assertTrue(valid_password_hash(ENCODED))
        self.assertTrue(verify_password(PASSWORD, ENCODED))
        self.assertFalse(verify_password("wrong password", ENCODED))
        self.assertFalse(valid_password_hash("bad"))
        token = create_session(os.environ["SESSION_SECRET"])
        self.assertTrue(verify_session(token, os.environ["SESSION_SECRET"]))
        self.assertFalse(verify_session(token + "x", os.environ["SESSION_SECRET"]))
        self.assertFalse(verify_session(token, "other-secret"))

    def test_distinct_enum_sets_do_not_collide(self):
        vault_type = metadata.tables["experience"].c.employment_type.type
        job_type = metadata.tables["job"].c.employment_type.type
        self.assertNotEqual(vault_type.name, job_type.name)
        self.assertIn("volunteer", vault_type.enums)
        self.assertNotIn("volunteer", job_type.enums)
        self.assertIn("unspecified", job_type.enums)

    def test_auth_cookie_login_and_logout(self):
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        with patch("app.api.auth.Redis.from_url", return_value=FakeRedis()):
            self.assertEqual(self.client.post("/api/auth/login", json={"password":""}).status_code, 422)
            self.assertEqual(self.client.post("/api/auth/login", json={"password":"wrong"}).status_code, 401)
            response = self.client.post("/api/auth/login", json={"password":PASSWORD})
            self.assertEqual(response.status_code, 200)
            self.assertIn("HttpOnly", response.headers["set-cookie"])
            self.assertIn("SameSite=lax", response.headers["set-cookie"])
            self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
            self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
            self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_rate_limit(self):
        with patch("app.api.auth.Redis.from_url", return_value=FakeRedis()):
            for _ in range(5):
                self.assertEqual(self.client.post("/api/auth/login", json={"password":"wrong"}).status_code, 401)
            self.assertEqual(self.client.post("/api/auth/login", json={"password":PASSWORD}).status_code, 429)

    def test_redis_failure_fails_closed(self):
        with patch("app.api.auth.Redis.from_url", side_effect=ConnectionError()):
            self.assertEqual(self.client.post("/api/auth/login", json={"password":PASSWORD}).status_code, 503)

    def test_origin_guard_and_standard_error(self):
        response = self.client.post("/api/auth/login", headers={"Origin":"https://untrusted.invalid"}, json={"password":PASSWORD})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(set(response.json()), {"code", "message", "details"})


class WorkflowChecks(unittest.TestCase):
    """Real route/service integration against an isolated SQLite adapter.

    Uses labeled synthetic fixtures only, never the owner's live database.
    Redis delivery is mocked; intake and tailoring tasks run directly.
    """
    def setUp(self):
        import asyncio
        import tempfile
        from pathlib import Path
        from conftest import database
        from app.db import get_session
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.engine,self.factory,self.dependency,initialize=database(self.root/'fixture.sqlite')
        asyncio.run(initialize())
        app.dependency_overrides[get_session]=self.dependency
        self.client=TestClient(app,raise_server_exceptions=True)
        self.auth=patch('app.api.auth.Redis.from_url',return_value=FakeRedis());self.auth.start()
        self.push=patch('app.services.job_service.queue_push');self.push.start()
        self.job_push=patch('app.api.jobs.queue_push');self.job_push.start()
        self.enqueue=patch('app.api.intake.enqueue');self.enqueue.start()
        self.client.post('/api/auth/login',json={'password':PASSWORD})
        self.original_data=get_settings().data_dir
        get_settings().data_dir=str(self.root/'data')

    def tearDown(self):
        import asyncio
        get_settings().data_dir=self.original_data
        self.enqueue.stop();self.push.stop();self.job_push.stop();self.auth.stop();app.dependency_overrides.clear()
        self.client.close();asyncio.run(self.engine.dispose());self.temp.cleanup()

    def request_ok(self,method,path,**kwargs):
        response=self.client.request(method,'/api'+path,**kwargs)
        self.assertLess(response.status_code,300,response.text)
        return response.json()

    def test_vault_intake_approval_master_and_resume(self):
        import asyncio
        from app.tasks.intake_tasks import process
        from app.tasks.tailoring_tasks import run
        from app.config import get_settings
        import pymupdf
        from docx import Document
        profile=self.request_ok('PUT','/vault/profile',json={'full_name':'Integration Fixture'})
        project=self.request_ok('POST','/vault/projects',json={'name':'Fixture API project','status':'shipped','visibility_priority':3,'solution_overview':'Built Python APIs.'})
        generated=self.request_ok('POST',f'/vault/projects/{project["id"]}/generate-facts')
        fact=generated['facts'][0]
        self.assertFalse(fact['is_verified_by_user'])
        self.assertEqual(self.request_ok('GET','/vault/completeness')[0]['verified_count'],0)
        self.request_ok('POST',f'/vault/facts/{fact["id"]}/verify')
        self.request_ok('POST','/vault/skills',json={'name':'Python','category':'language','proficiency':'working','claim_allowed':True})
        self.assertEqual(self.request_ok('GET','/vault/completeness')[0]['verified_count'],1)
        self.assertEqual(len(self.request_ok('GET','/vault/resume-variants')),5)
        source='Integration fixture only.\nCompany: Fixture Co\nRole: Python Developer\nRequired skills: Python, Kubernetes\nResponsibilities: Build APIs for customers.'
        intake=self.request_ok('POST','/intake',data={'input_type':'text','text':source})
        self.assertEqual(self.request_ok('GET','/jobs')['total'],0)
        with patch('app.tasks.intake_tasks.session_factory',self.factory):asyncio.run(process(intake['intake_id']))
        reviewed=self.request_ok('GET',f'/intake/{intake["intake_id"]}')
        self.assertEqual(reviewed['status'],'needs_review')
        self.assertEqual(reviewed['extraction_json']['title']['value'],'Python Developer')
        self.request_ok('PUT',f'/intake/{intake["intake_id"]}/fields',json={'title':'Python Developer','company_name':'Fixture Co','required_skills':['Python','Kubernetes']})
        approved=self.request_ok('POST',f'/intake/{intake["intake_id"]}/approve',json={})
        repeated=self.request_ok('POST',f'/intake/{intake["intake_id"]}/approve',json={})
        self.assertEqual(approved,repeated)
        job_id=approved['job_id'];self.assertEqual(self.request_ok('GET','/jobs')['total'],1)
        self.request_ok('PATCH',f'/jobs/{job_id}/master',json={'status':'applied','my_notes':'Integration test only'})
        self.assertTrue(self.request_ok('GET',f'/jobs/{job_id}')['master']['applied_on'])
        self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}/history')[0]['to_status'],'applied')
        self.assertIn('Job ID,Status,Priority',self.client.get('/api/jobs/export.csv').text)
        with patch('app.tasks.tailoring_tasks.run_tailoring.delay'):
            result=self.request_ok('POST',f'/jobs/{job_id}/tailor',json={'max_pages':1,'include_summary':False})
        resume_id=result['tailored_resume_id']
        with patch('app.tasks.tailoring_tasks.session_factory',self.factory):asyncio.run(run(resume_id))
        resume=self.request_ok('GET',f'/tailored/{resume_id}')
        self.assertEqual(resume['status'],'ready',resume['validation_report_json'])
        self.assertEqual(resume['coverage_json']['must_have_coverage'],.5)
        self.assertEqual(resume['coverage_json']['not_in_vault'][0]['term'],'Kubernetes')
        with pymupdf.open(resume['pdf_path']) as pdf:
            self.assertEqual(pdf.page_count,1);self.assertIn('Built Python APIs.',pdf[0].get_text())
        self.assertIn('Built Python APIs.',' '.join(p.text for p in Document(resume['docx_path']).paragraphs))
        bullet=resume['sections_json']['projects'][0]['bullets'][0]
        self.assertEqual(self.client.patch(f'/api/tailored/{resume_id}/bullet',json={'bullet_key':bullet['key'],'new_text':'Built 80 Kubernetes APIs.'}).status_code,422)
        self.assertEqual(self.client.get(f'/api/tailored/{resume_id}/preview').headers['content-type'],'image/png')
        self.assertEqual(self.client.patch(f'/api/vault/facts/{fact["id"]}',json={'text':'Changed claim'}).status_code,409)
        self.request_ok('PATCH',f'/tailored/{resume_id}/bullet',json={'bullet_key':bullet['key'],'new_text':'Developed Python APIs.'})
        self.assertEqual(self.request_ok('GET',f'/tailored/{resume_id}')['status'],'needs_render')
        with patch('app.tasks.tailoring_tasks.render_resume.delay'):
            self.request_ok('POST',f'/tailored/{resume_id}/render')
        with patch('app.tasks.tailoring_tasks.session_factory',self.factory):asyncio.run(run(resume_id,True))
        self.assertEqual(self.request_ok('GET',f'/tailored/{resume_id}')['status'],'ready')
        self.request_ok('POST',f'/tailored/{resume_id}/mark-final')
        self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}')['master']['resume_version_id'],resume_id)
        # Exercise the real sync implementation with a fake remote Sheet, not a fake DB.
        from app.services.sheets_sync import HEADERS,push_pending,pull
        import copy
        import re
        class FakeSheets:
            rows_data=[HEADERS.copy()]
            def __init__(self,config):pass
            def area(self,cells='A:AG'):return "'Jobs'!"+cells
            async def rows(self):return copy.deepcopy(self.rows_data)
            async def setup(self):return {'ok':True}
            async def call(self,method,path='',body=None):
                if ':append' in path:
                    start=len(self.rows_data)+1;self.rows_data.extend(copy.deepcopy(body['values']))
                    return {'updates':{'updatedRange':f"'Jobs'!A{start}:AG{len(self.rows_data)}"}}
                if path=='/values:batchUpdate':
                    for item in body['data']:
                        index=int(re.search(r'!A(\d+)',item['range']).group(1))-1
                        self.rows_data[index]=copy.deepcopy(item['values'][0])
                    return {}
                raise AssertionError('Unexpected fake Sheet call: '+path)
        self.request_ok('PUT','/sheets/settings',json={'google_sheet_id':'fixture-sheet-id','google_sheet_tab_name':'Jobs'})
        async def push_run():
            async with self.factory() as session:return await push_pending(session)
        async def pull_run():
            async with self.factory() as session:return await pull(session)
        with patch('app.services.sheets_sync.Sheets',FakeSheets):
            self.assertEqual(asyncio.run(push_run())['synced'],1)
            self.assertEqual(len(FakeSheets.rows_data),2)
            self.assertEqual(asyncio.run(push_run())['synced'],0)
            self.assertEqual(len(FakeSheets.rows_data),2)
            FakeSheets.rows_data[1][1]='interviewing'
            self.assertEqual(asyncio.run(pull_run())['updated'],1)
            self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}')['master']['status'],'interviewing')
            self.request_ok('PATCH',f'/jobs/{job_id}/master',json={'status':'offer'})
            FakeSheets.rows_data[1][1]='rejected'
            self.assertEqual(asyncio.run(pull_run())['conflicts'],1)
            self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}')['master']['status'],'offer')
            master_id=self.request_ok('GET',f'/jobs/{job_id}')['master']['id']
            self.request_ok('POST',f'/sheets/conflicts/{master_id}/resolve',json={'choice':'app'})
            self.assertEqual(asyncio.run(push_run())['synced'],1)
            self.assertEqual(FakeSheets.rows_data[1][1],'offer')
            FakeSheets.rows_data[1][1]='invalid-status'
            self.assertEqual(asyncio.run(pull_run())['rejected'],1)
            self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}')['master']['status'],'offer')
            FakeSheets.rows_data.pop()
            asyncio.run(pull_run())
            self.assertEqual(self.request_ok('GET',f'/jobs/{job_id}')['master']['sheet_sync_state'],'failed')
            self.assertEqual(asyncio.run(push_run())['synced'],1)
            self.assertEqual(len(FakeSheets.rows_data),2)
        self.request_ok('DELETE',f'/jobs/{job_id}')
        self.assertEqual(self.request_ok('GET','/jobs')['total'],0)
        self.assertTrue(self.request_ok('GET',f'/jobs/{job_id}')['job']['is_deleted'])


from app.config import get_settings

if __name__ == "__main__":
    unittest.main()
