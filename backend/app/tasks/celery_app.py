from celery import Celery
from app.config import get_settings

settings = get_settings()
celery = Celery("job_portal", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(timezone="UTC", enable_utc=True, task_serializer="json", result_serializer="json", accept_content=["json"], broker_connection_retry_on_startup=True)
celery.conf.broker_connection_timeout = 2
celery.conf.task_publish_retry = False
celery.conf.broker_transport_options = {"socket_connect_timeout": 2, "socket_timeout": 2, "max_retries": 0}
celery.conf.imports = ('app.tasks.intake_tasks', 'app.tasks.sheet_tasks', 'app.tasks.tailoring_tasks')
celery.conf.beat_schedule = {'retry-sheet-push-every-five-minutes': {'task': 'push_pending', 'schedule': 300.0}}
