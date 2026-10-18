from app.models.base import *

sheet_sync_log = table("sheet_sync_log", choice("direction", "push pull"), ref("master_row_id", "master_row.id", required=False), choice("action", "append update skip conflict error"), field("detail"))
app_setting = table("app_setting", field("key", required=True, unique=True), field("value"))
