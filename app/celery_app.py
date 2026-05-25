import os

from celery import Celery


def _redis_url() -> str:
    return (
        os.getenv("CELERY_BROKER_URL")
        or os.getenv("REDIS_URL")
        or "redis://chatwoot_redis:6379/1"
    )


celery_app = Celery(
    "hr_capital_humano",
    broker=_redis_url(),
    backend=os.getenv("CELERY_RESULT_BACKEND", _redis_url()),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=os.getenv("TZ", "America/Monterrey"),
    enable_utc=True,
    task_default_queue="inbound",
    worker_prefetch_multiplier=1,
    task_acks_late=False,
)
