"""
Celery application configuration with Beat schedule.

Run worker:  celery -A app.celery_app worker --loglevel=info
Run beat:    celery -A app.celery_app beat --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "ambycrm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.member_sync"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # Beat schedule
    beat_schedule={
        # Clean up expired and inactive cache rows every hour
        "cleanup-expired-cache": {
            "task": "app.tasks.member_sync.cleanup_expired_cache",
            "schedule": crontab(minute=0),  # every hour on the hour
        },
        # Refresh caches for recently-active members every 4 hours
        "refresh-active-members": {
            "task": "app.tasks.member_sync.refresh_active_members_cache",
            "schedule": crontab(minute=0, hour="*/4"),  # every 4 hours
        },
    },
)
