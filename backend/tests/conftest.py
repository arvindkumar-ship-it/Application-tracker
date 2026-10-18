"""Isolated SQLite adapter for portable tests; production always uses PostgreSQL.

Array values preserve the PostgreSQL ARRAY API. Advisory locks are replaced only
in this adapter, so these tests do not claim to verify PostgreSQL concurrency.
"""
import json
import re
from sqlalchemy import event,Boolean,DefaultClause,text
from sqlalchemy.dialects.postgresql import ARRAY,JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.pool import NullPool
from app.models import metadata


@compiles(ARRAY,'sqlite')
def compile_array(type_,compiler,**kwargs): return 'TEXT'


@compiles(JSONB,'sqlite')
def compile_json(type_,compiler,**kwargs): return 'JSON'


class TestArray(ARRAY):
    cache_ok=True
    def bind_processor(self,dialect):
        if dialect.name=='sqlite': return lambda value:json.dumps(value) if value is not None else None
        return super().bind_processor(dialect)
    def result_processor(self,dialect,coltype):
        if dialect.name=='sqlite': return lambda value:(json.loads(value) or []) if value else []
        return super().result_processor(dialect,coltype)


def database(path):
    for table in metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type,ARRAY) and not isinstance(column.type,TestArray): column.type=TestArray(column.type.item_type)
            if isinstance(column.type,Boolean) and column.server_default is not None:
                value=str(column.server_default.arg).lower()
                if value in {'false','true'}: column.server_default=DefaultClause(text('1' if value=='true' else '0'))
    engine=create_async_engine('sqlite+aiosqlite:///'+str(path).replace('\\','/'),poolclass=NullPool)
    @event.listens_for(engine.sync_engine,'before_cursor_execute',retval=True)
    def advisory(connection,cursor,statement,parameters,context,executemany):
        if 'pg_advisory_xact_lock' in statement: return 'SELECT 1',()
        return statement,parameters
    async def initialize():
        async with engine.begin() as connection: await connection.run_sync(metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async def session():
        async with factory() as value: yield value
    return engine,factory,session,initialize
