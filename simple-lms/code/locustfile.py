from locust import HttpUser, between, task


class LMSApiUser(HttpUser):
    wait_time = between(1, 3)

    @task(5)
    def list_courses(self):
        self.client.get("/api/courses", params={"limit": 10, "offset": 0}, name="/api/courses")

    @task(3)
    def search_courses(self):
        self.client.get(
            "/api/courses",
            params={"search": "Django", "limit": 10, "offset": 0},
            name="/api/courses?search",
        )

    @task(2)
    def course_detail(self):
        self.client.get("/api/courses/1", name="/api/courses/{id}")

    @task(1)
    def api_docs(self):
        self.client.get("/api/docs", name="/api/docs")
