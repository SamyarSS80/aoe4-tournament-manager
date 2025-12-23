import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aoe_tour.settings")

app = Celery("aoe_tour")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
