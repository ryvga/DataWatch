from celery import Celery

from app.config import settings

celery_app = Celery(
    "datawatch",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks"],
)

from celery.schedules import crontab

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "cleanup-old-profiles-daily": {
            "task": "tasks.cleanup_old_profiles",
            "schedule": crontab(hour=3, minute=0),  # 3am UTC daily
        },
        "send-daily-digests-hourly": {
            "task": "tasks.send_daily_digests",
            "schedule": crontab(minute=0),  # every hour at :00
        },
        "generate-weekly-summaries": {
            "task": "tasks.generate_weekly_summaries",
            "schedule": crontab(hour=6, minute=0, day_of_week=1),  # Monday 6am UTC
        },
    },
)
