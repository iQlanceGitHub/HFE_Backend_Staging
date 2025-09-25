from celery import Celery

celery_app = Celery(
    "notification_tasks",
    broker="redis://redis:6379/0",
    backend="redis://redis:6379/0",
    include=["src.common.tasks"],
)
