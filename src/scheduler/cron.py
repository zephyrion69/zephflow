import logging
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_CRON_FIELD_COUNT = 5


class CronScheduler:
    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Cron scheduler started")

    def shutdown(self, wait: bool = True) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=wait)
            logger.info("Cron scheduler stopped")

    def add_job(
        self,
        func: Callable[..., Any],
        cron_expression: str,
        job_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        parts = cron_expression.split()
        if len(parts) != _CRON_FIELD_COUNT:
            raise ValueError(
                f"Invalid cron expression '{cron_expression}'. "
                "Expected 5 fields: minute hour day month day_of_week"
            )
        minute, hour, day, month, day_of_week = parts
        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
        )
        job = self._scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            replace_existing=True,
            kwargs=kwargs,
        )
        logger.info("Scheduled job '%s' with cron '%s'", job.id, cron_expression)
        return str(job.id)

    def remove_job(self, job_id: str) -> None:
        self._scheduler.remove_job(job_id)
        logger.info("Removed scheduled job '%s'", job_id)

    def list_jobs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None,
            }
            for job in self._scheduler.get_jobs()
        ]

    @property
    def running(self) -> bool:
        return bool(self._scheduler.running)


scheduler = CronScheduler()
