from celery import shared_task

from .services import recrawl_sources


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def recrawl_all_sources(self, limit=500):
    """Celery entry point for the scheduled three-hour marketplace refresh."""
    return recrawl_sources("all", limit=limit)
