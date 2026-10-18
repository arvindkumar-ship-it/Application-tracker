import asyncio
import json
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import HTTPException
from sqlalchemy import select,insert,update,text
from app.config import get_settings
from app.models.sync import app_setting,sheet_sync_log
from app.models.job import job,master_row,status_history,JOB_STATUSES,PRIORITIES
from app.models.tailoring import tailored_resume
from app.services.job_service import get_joined

HEADERS=['Job ID','Status','Priority','Company','Role','Employment Type','Work Mode','Location','Stipend/Salary (as written)','Duration','Experience Required','Deadline','Posted','Apply Link','Apply Email','Contact Name','Contact Email','Contact Phone','Required Skills','Preferred Skills','Responsibilities','Qualifications','Perks','Selection Process','Source Platform','Source Link','Applied On','Follow-up On','My Notes','Interview Notes','Resume Version','Added On','Last Updated']
EDIT_INDEX={'status':1,'priority':2,'applied_on':26,'follow_up_on':27,'my_notes':28,'interview_notes':29}


def row_values(j,m):
    values=[str(j['id']),m['status'],m['priority'],j['company_name'],j['title'],j['employment_type'],j['work_mode'],j['location_text'],j['stipend_or_salary_text'],j['duration_text'],j['experience_required_text'],j['application_deadline'],j['posted_date'],j['apply_url'],j['apply_email'],j['contact_name'],j['contact_email'],j['contact_phone'],', '.join(j['required_skills']),', '.join(j['preferred_skills']),'\n'.join(j['responsibilities']),'\n'.join(j['qualifications']),'\n'.join(j['perks_benefits']),j['selection_process_text'],j['source_platform'],j['source_url'],m['applied_on'],m['follow_up_on'],m['my_notes'],m['interview_notes'],j.get('_resume_filename',''),j['created_at'],j['updated_at']]
    return [x.isoformat() if isinstance(x,(date,datetime)) else '' if x is None else str(x) for x in values]


def compare(sheet,db,snapshot):
    changes={};conflicts={}
    for field in EDIT_INDEX:
        s=str(sheet.get(field) or '');d=str(db.get(field) or '');b=str(snapshot.get(field) or '')
        if s==b or s==d: continue
        if d==b: changes[field]=s
        else: conflicts[field]={'app':d,'sheet':s,'baseline':b}
    return changes,conflicts


def validate_editable(values):
    result={}
    for key,value in values.items():
        if key=='status' and value not in JOB_STATUSES.split(): raise ValueError('Invalid status in Sheet')
        if key=='priority' and value not in PRIORITIES.split(): raise ValueError('Invalid priority in Sheet')
        if key in {'applied_on','follow_up_on'}: value=date.fromisoformat(value) if value else None
        result[key]=value
    return result


async def settings(session):
    return dict((await session.execute(select(app_setting.c.key,app_setting.c.value))).all())


class Sheets:
    def __init__(self,config):
        self.sheet_id=config.get('google_sheet_id','');self.tab=config.get('google_sheet_tab_name') or 'Jobs'
        self.base=f'https://sheets.googleapis.com/v4/spreadsheets/{self.sheet_id}'
        self.token=None

    async def call(self,method,path='',body=None):
        if not self.sheet_id: raise ValueError('Set your Google Sheet ID in Settings first')
        if not self.token:
            from google.oauth2.service_account import Credentials
            from google.auth.transport.requests import Request
            path_to_key=get_settings().google_service_account_json_path
            if not Path(path_to_key).is_file(): raise ValueError('Service-account key file is not mounted. Follow the Settings setup instructions.')
            def token():
                credential=Credentials.from_service_account_file(path_to_key,scopes=['https://www.googleapis.com/auth/spreadsheets'])
                credential.refresh(Request());return credential.token
            self.token=await asyncio.to_thread(token)
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.request(method,self.base+path,headers={'Authorization':'Bearer '+self.token},json=body)
        if response.is_error:
            try: message=response.json()['error']['message']
            except (ValueError,KeyError): message='Google Sheets request failed'
            raise ValueError(f'Google Sheets {response.status_code}: {message}')
        return response.json()

    def area(self,cells='A:AG'):
        return "'"+self.tab.replace("'","''")+"'!"+cells

    async def rows(self):
        return (await self.call('GET','/values/'+quote(self.area(),safe=''))).get('values',[])

    async def setup(self):
        meta=await self.call('GET')
        matching=[x['properties'] for x in meta['sheets'] if x['properties']['title']==self.tab]
        if not matching:
            created=await self.call('POST',':batchUpdate',{'requests':[{'addSheet':{'properties':{'title':self.tab}}}]})
            matching=[created['replies'][0]['addSheet']['properties']]
        rows=await self.rows()
        if rows and rows[0]!=HEADERS: raise ValueError('The Sheet header differs from the required A:AG columns. Use an empty tab to avoid overwriting existing data.')
        if not rows: await self.call('POST','/values:batchUpdate',{'valueInputOption':'RAW','data':[{'range':self.area('A1:AG1'),'values':[HEADERS]}]})
        sid=matching[0]['sheetId']
        requests=[{'updateSheetProperties':{'properties':{'sheetId':sid,'gridProperties':{'frozenRowCount':1}},'fields':'gridProperties.frozenRowCount'}},{'setBasicFilter':{'filter':{'range':{'sheetId':sid,'startRowIndex':0,'startColumnIndex':0,'endColumnIndex':33}}}}]
        for index,choices in [(1,JOB_STATUSES.split()),(2,PRIORITIES.split())]:
            requests.append({'setDataValidation':{'range':{'sheetId':sid,'startRowIndex':1,'startColumnIndex':index,'endColumnIndex':index+1},'rule':{'condition':{'type':'ONE_OF_LIST','values':[{'userEnteredValue':x} for x in choices]},'strict':True,'showCustomUi':True}}})
        await self.call('POST',':batchUpdate',{'requests':requests})
        return {'ok':True,'message':'Connection verified. Header, filters and dropdowns are ready.'}


async def log(session,direction,row_id,action,detail):
    await session.execute(insert(sheet_sync_log).values(direction=direction,master_row_id=row_id,action=action,detail=detail))


async def apply_sheet_changes(session,m,changes):
    values=validate_editable(changes)
    if values.get('status')=='applied' and not m['applied_on'] and not values.get('applied_on'):
        from zoneinfo import ZoneInfo
        values['applied_on']=datetime.now(ZoneInfo('Asia/Kolkata')).date()
    if values.get('status') and values['status']!=m['status']:
        await session.execute(insert(status_history).values(master_row_id=m['id'],from_status=m['status'],to_status=values['status'],changed_via='sheet_pull'))
    if values: await session.execute(update(master_row).where(master_row.c.id==m['id']).values(**values))
    return values


async def push_pending(session,only_id=None):
    config=await settings(session)
    if not config.get('google_sheet_id'): return {'pending':True,'message':'Google Sheet is not configured. Your app data is safe.'}
    await session.execute(text('SELECT pg_advisory_xact_lock(71236002)'))
    client=Sheets(config);rows=await client.rows()
    if not rows or rows[0]!=HEADERS: await client.setup();rows=await client.rows()
    index={r[0]:(i+1,r) for i,r in enumerate(rows) if i and r and r[0]}
    query=select(master_row).where(master_row.c.sheet_sync_state.in_(['pending','failed']))
    if only_id:
        from app.services.vault_service import identifier
        query=query.where(master_row.c.id==identifier(only_id))
    masters=(await session.execute(query.with_for_update())).mappings().all();updates=[];completed=[];appends=[]
    for m in masters:
        joined=await get_joined(session,m['job_id']);j=joined['job'];m=dict(m)
        existing=index.get(str(j['id']))
        if existing and m['last_pushed_snapshot']:
            row_no,remote=existing;remote=remote+['']*(33-len(remote));sheet={k:remote[i] for k,i in EDIT_INDEX.items()}
            current={k:m[k].isoformat() if isinstance(m[k],date) else m[k] for k in EDIT_INDEX}
            changes,conflicts=compare(sheet,current,m['last_pushed_snapshot'])
            if conflicts:
                await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='conflict'))
                await log(session,'push',m['id'],'conflict',json.dumps({'fields':conflicts,'sheet':sheet}));continue
            if changes:
                try: m.update(await apply_sheet_changes(session,m,changes))
                except ValueError as e:
                    await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='failed'));await log(session,'push',m['id'],'error',str(e));continue
        if m['resume_version_id']:
            filename=(await session.execute(select(tailored_resume.c.pdf_path).where(tailored_resume.c.id==m['resume_version_id']))).scalar_one_or_none()
            j['_resume_filename']=Path(filename).name if filename else ''
        values=row_values(j,m)
        if existing:
            number=existing[0];updates.append({'range':client.area(f'A{number}:AG{number}'),'values':[values]})
        else:
            number=None;appends.append(values)
        completed.append((m,values,number))
    if appends:
        # Reserve append positions through the Sheet API, then update all pending data in one batch.
        result=await client.call('POST','/values/'+quote(client.area(),safe='')+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS',{'values':appends})
        import re
        start=int(re.search(r'![A-Z]+(\d+)',result['updates']['updatedRange']).group(1));next_number=start
        completed=[(m,values,(number if number is not None else next_number+sum(1 for prev in completed[:i] if prev[2] is None))) for i,(m,values,number) in enumerate(completed)]
    if updates: await client.call('POST','/values:batchUpdate',{'valueInputOption':'RAW','data':updates})
    for m,values,number in completed:
        snapshot={key:values[index] for key,index in EDIT_INDEX.items()}
        await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='synced',sheet_row_number=number,last_pushed_snapshot=snapshot,last_synced_at=datetime.now(timezone.utc)))
        await log(session,'push',m['id'],'update' if str(m['job_id']) in index else 'append','Row synchronized by Job ID')
    await session.commit();return {'synced':len(completed)}


async def pull(session):
    await session.execute(text('SELECT pg_advisory_xact_lock(71236002)'))
    client=Sheets(await settings(session));rows=await client.rows()
    if not rows or rows[0]!=HEADERS: raise ValueError('Sheet headers do not match. Test the connection first.')
    report={'updated':0,'conflicts':0,'rejected':0,'ignored':[]}
    remote={row[0]:row+['']*(33-len(row)) for row in rows[1:] if row and row[0]}
    known=set()
    for m in (await session.execute(select(master_row).with_for_update())).mappings():
        key=str(m['job_id']);known.add(key)
        if key not in remote:
            await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='failed'));await log(session,'pull',m['id'],'error','row missing in sheet');continue
        sheet={k:remote[key][i] for k,i in EDIT_INDEX.items()};db={k:m[k].isoformat() if isinstance(m[k],date) else m[k] for k in EDIT_INDEX}
        changes,conflicts=compare(sheet,db,m['last_pushed_snapshot'])
        try: validate_editable(sheet)
        except ValueError as e:
            report['rejected']+=1;await log(session,'pull',m['id'],'error',str(e));await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='failed'));continue
        if conflicts:
            report['conflicts']+=1;await log(session,'pull',m['id'],'conflict',json.dumps({'fields':conflicts,'sheet':sheet}));await session.execute(update(master_row).where(master_row.c.id==m['id']).values(sheet_sync_state='conflict'));continue
        if changes:
            await apply_sheet_changes(session,m,changes);report['updated']+=1;await log(session,'pull',m['id'],'update','Accepted Sheet changes through three-way comparison')
        # Preserve the baseline for app-only edits so a later push still detects concurrency.
        if all(str(db[k] or '')==str(m['last_pushed_snapshot'].get(k) or '') or str(db[k] or '')==str(sheet[k] or '') for k in EDIT_INDEX):
            await session.execute(update(master_row).where(master_row.c.id==m['id']).values(last_pushed_snapshot=sheet,sheet_sync_state='synced',last_synced_at=datetime.now(timezone.utc)))
    report['ignored']=[{'row':i+2,'reason':'No known Job ID'} for i,row in enumerate(rows[1:]) if not row or not row[0] or row[0] not in known]
    await session.execute(update(app_setting).where(app_setting.c.key=='last_pull_at').values(value=datetime.now(timezone.utc).isoformat()))
    if not (await session.execute(select(app_setting.c.id).where(app_setting.c.key=='last_pull_at'))).first(): await session.execute(insert(app_setting).values(key='last_pull_at',value=datetime.now(timezone.utc).isoformat()))
    await session.commit();return report
