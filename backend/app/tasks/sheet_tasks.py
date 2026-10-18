import asyncio
from sqlalchemy import update,select
from app.tasks.celery_app import celery
from app.db import session_factory
from app.models.job import master_row
from app.services.vault_service import identifier


async def run_push(row_id=None):
    from app.services.sheets_sync import push_pending,log
    async with session_factory() as session:
        try: return await push_pending(session,row_id)
        except Exception as e:
            await session.rollback()
            query=select(master_row.c.id).where(master_row.c.sheet_sync_state.in_(['pending','failed']))
            if row_id: query=query.where(master_row.c.id==identifier(row_id))
            ids=(await session.execute(query)).scalars().all()
            for row in ids:
                await session.execute(update(master_row).where(master_row.c.id==row).values(sheet_sync_state='failed'))
                await log(session,'push',row,'error',str(e)[:500] if isinstance(e,ValueError) else 'Sheet connection unavailable; retry pending')
            await session.commit()
            raise


@celery.task(name='push_row_to_sheet',bind=True,max_retries=5)
def push_row_to_sheet(self,row_id):
    try: return asyncio.run(run_push(row_id))
    except Exception: raise self.retry(countdown=min(300,10*2**self.request.retries))


@celery.task(name='push_pending')
def push_pending():
    try: return asyncio.run(run_push())
    except Exception: return {'failed':True}


@celery.task(name='pull_from_sheet')
def pull_from_sheet():
    from app.services.sheets_sync import pull
    async def run():
        async with session_factory() as session: return await pull(session)
    return asyncio.run(run())
