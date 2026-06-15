from locust import HttpUser, between, task


class CareWiseUser(HttpUser):
    wait_time = between(1, 3)

    @task(3)
    def health(self):
        self.client.get("/health")

    @task(1)
    def ready(self):
        self.client.get("/ready")
