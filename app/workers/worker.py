from redis import Redis
from rq import Worker

from app.core.config import settings


def main():
    redis = Redis.from_url(settings.redis_url)
    worker = Worker(["carewise-default"], connection=redis)
    worker.work()


if __name__ == "__main__":
    main()
