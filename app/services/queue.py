from rq import Queue
from redis import Redis

from app.core.config import settings


def get_queue() -> Queue:
    return Queue("carewise-default", connection=Redis.from_url(settings.redis_url))


def enqueue_care_plan_generation(actor_id: str, payload: dict) -> str:
    queue = get_queue()
    job = queue.enqueue("app.workers.tasks.generate_care_plan_task", actor_id, payload)
    return job.id
