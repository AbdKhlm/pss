import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.core.cache import cache
from django.conf import settings
from django.test import TestCase
from ninja.errors import HttpError

from core.apiv1 import rate_limit
from core.mongo import get_learning_analytics, log_activity
from core.tasks import (
    export_course_report,
    generate_certificate,
    send_enrollment_email,
    update_course_statistics,
)
from core.utils import is_admin, is_instructor, is_student
from courses.models import Course, User
from courses.test_factories import TestDataFactory


class RoleDecoratorTests(TestCase):
    def _request_for_role(self, role, authenticated=True):
        return SimpleNamespace(
            user=SimpleNamespace(
                is_authenticated=authenticated,
                role=role,
            )
        )

    def test_is_admin_allows_admin_user(self):
        @is_admin
        def protected_view(request):
            return "ok"

        response = protected_view(self._request_for_role("admin"))
        self.assertEqual(response, "ok")

    def test_is_instructor_rejects_student(self):
        @is_instructor
        def protected_view(request):
            return "ok"

        with self.assertRaises(HttpError) as context:
            protected_view(self._request_for_role("student"))

        self.assertEqual(context.exception.status_code, 403)

    def test_is_student_rejects_unauthenticated_user(self):
        @is_student
        def protected_view(request):
            return "ok"

        with self.assertRaises(HttpError) as context:
            protected_view(self._request_for_role("student", authenticated=False))

        self.assertEqual(context.exception.status_code, 401)


class MongoHelperTests(TestCase):
    def test_log_activity_inserts_expected_document(self):
        db = Mock()
        db.activity_log.insert_one.return_value.inserted_id = "mongo-id"

        with patch("core.mongo.get_mongo_db", return_value=db):
            inserted_id = log_activity(
                user_id=10,
                user_role="student",
                action="TEST_ACTION",
                course_id=2,
                lesson_id=3,
                metadata={"source": "test"},
            )

        self.assertEqual(inserted_id, "mongo-id")
        inserted_document = db.activity_log.insert_one.call_args.args[0]
        self.assertEqual(inserted_document["user_id"], 10)
        self.assertEqual(inserted_document["action"], "TEST_ACTION")
        self.assertEqual(inserted_document["metadata"]["source"], "test")

    def test_get_learning_analytics_builds_match_stage_when_course_filter_is_given(self):
        db = Mock()
        db.activity_log.aggregate.return_value = [{"_id": 1, "total_actions": 4, "unique_user_count": 2}]

        with patch("core.mongo.get_mongo_db", return_value=db):
            result = get_learning_analytics(course_id=1)

        pipeline = db.activity_log.aggregate.call_args.args[0]
        self.assertEqual(pipeline[0], {"$match": {"course_id": 1}})
        self.assertEqual(result[0]["total_actions"], 4)

    def test_get_mongo_db_uses_configured_connection_settings(self):
        fake_client = MagicMock()

        with patch("core.mongo.MongoClient", return_value=fake_client) as mocked_client:
            from core.mongo import get_mongo_db

            db = get_mongo_db()

        mocked_client.assert_called_once_with(settings.MONGODB_URI)
        self.assertIs(db, fake_client.__getitem__.return_value)


class CeleryTaskTests(TestCase):
    @patch("core.tasks.send_mail")
    def test_send_enrollment_email_uses_django_mail(self, mocked_send_mail):
        send_enrollment_email("student@example.com", "Django API")

        mocked_send_mail.assert_called_once()
        _, kwargs = mocked_send_mail.call_args
        self.assertEqual(kwargs["recipient_list"], ["student@example.com"])

    def test_generate_certificate_returns_status_payload(self):
        result = generate_certificate(1, 2)

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["student_id"], 1)
        self.assertEqual(result["course_id"], 2)

    def test_update_course_statistics_returns_course_count(self):
        TestDataFactory.create_course(name="Course One")
        TestDataFactory.create_course(name="Course Two")

        result = update_course_statistics()

        self.assertEqual(result["status"], "done")
        self.assertEqual(result["courses_updated"], 2)

    def test_export_course_report_generates_csv_content(self):
        student = TestDataFactory.create_user(role="student", username="csvstudent")
        course = TestDataFactory.create_course(name="CSV Course")
        lesson = TestDataFactory.create_lesson(course=course, order=1)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)
        TestDataFactory.create_progress(
            enrollment=enrollment,
            student=student,
            lesson=lesson,
            completed=True,
        )

        report = export_course_report(course.id)

        self.assertIn("Student Username", report)
        self.assertIn("csvstudent", report)
        self.assertIn("100.0", report)


class RateLimitTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_rate_limit_raises_http_error_when_limit_is_exceeded(self):
        request = SimpleNamespace(META={"REMOTE_ADDR": "127.0.0.1"})

        rate_limit(request, limit=1, period=60)

        with self.assertRaises(HttpError) as context:
            rate_limit(request, limit=1, period=60)

        self.assertEqual(context.exception.status_code, 429)


class ApiIntegrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.instructor_password = "TeachPass123!"
        self.student_password = "StudPass123!"
        self.admin_password = "AdminPass123!"

        self.instructor = TestDataFactory.create_user(
            username="instructor_api",
            email="instructor_api@example.com",
            password=self.instructor_password,
            role="instructor",
        )
        self.student = TestDataFactory.create_user(
            username="student_api",
            email="student_api@example.com",
            password=self.student_password,
            role="student",
        )
        self.admin = TestDataFactory.create_user(
            username="admin_api",
            email="admin_api@example.com",
            password=self.admin_password,
            role="admin",
        )
        self.category = TestDataFactory.create_category(name="Backend")
        self.course = TestDataFactory.create_course(
            name="Django API",
            instructor=self.instructor,
            category=self.category,
        )
        self.lesson = TestDataFactory.create_lesson(course=self.course, order=1, title="Intro API")

    def auth_header(self, username, password):
        response = self.client.post(
            "/api/auth/sign-in",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        token = response.json()["access"]
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    @patch("core.apiv1.log_activity")
    def test_register_endpoint_creates_user(self, mocked_log_activity):
        response = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": "newstudent",
                    "first_name": "New",
                    "last_name": "Student",
                    "email": "newstudent@example.com",
                    "password": "NewStudent123!",
                    "role": "student",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(mocked_log_activity.called)
        self.assertTrue(User.objects.filter(username="newstudent").exists())

    @patch("core.apiv1.log_activity")
    def test_auth_me_returns_authenticated_user(self, mocked_log_activity):
        headers = self.auth_header(self.instructor.username, self.instructor_password)
        response = self.client.get("/api/auth/me", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["username"], self.instructor.username)
        mocked_log_activity.assert_called_once()

    def test_list_courses_populates_cache(self):
        response = self.client.get("/api/courses", {"search": "Django", "limit": 10, "offset": 0})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()), 1)
        self.assertIsNotNone(cache.get("courses_list:Django::10:0"))

    @patch("core.apiv1.log_activity")
    def test_get_course_detail_returns_contents(self, mocked_log_activity):
        response = self.client.get(f"/api/courses/{self.course.id}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["contents"][0]["title"], "Intro API")
        mocked_log_activity.assert_called_once()

    @patch("core.apiv1.log_activity")
    def test_create_course_requires_instructor_or_admin(self, mocked_log_activity):
        headers = self.auth_header(self.student.username, self.student_password)
        response = self.client.post(
            "/api/courses",
            data=json.dumps(
                {
                    "name": "Forbidden Course",
                    "description": "Should fail",
                    "price": 50000,
                    "category_id": self.category.id,
                }
            ),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 403, response.content)
        mocked_log_activity.assert_not_called()

    @patch("core.apiv1.log_activity")
    def test_create_course_as_instructor_succeeds(self, mocked_log_activity):
        headers = self.auth_header(self.instructor.username, self.instructor_password)
        response = self.client.post(
            "/api/courses",
            data=json.dumps(
                {
                    "name": "Testing Course",
                    "description": "Created from automated test",
                    "price": 120000,
                    "category_id": self.category.id,
                }
            ),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(Course.objects.filter(name="Testing Course").exists())
        mocked_log_activity.assert_called_once()

    @patch("core.apiv1.log_activity")
    def test_patch_course_supports_partial_update(self, mocked_log_activity):
        headers = self.auth_header(self.instructor.username, self.instructor_password)
        response = self.client.patch(
            f"/api/courses/{self.course.id}",
            data=json.dumps({"price": 150000}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.course.refresh_from_db()
        self.assertEqual(self.course.price, 150000)
        mocked_log_activity.assert_called_once()

    @patch("core.apiv1.log_activity")
    @patch("core.apiv1.send_enrollment_email.delay")
    def test_enroll_endpoint_creates_enrollment_and_queues_email(self, mocked_delay, mocked_log_activity):
        headers = self.auth_header(self.student.username, self.student_password)
        new_course = TestDataFactory.create_course(
            name="Celery Course",
            instructor=self.instructor,
            category=self.category,
        )
        response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": new_course.id}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(new_course.enrollments.filter(student=self.student).exists())
        mocked_delay.assert_called_once()
        mocked_log_activity.assert_called_once()

    @patch("core.apiv1.log_activity")
    @patch("core.apiv1.generate_certificate.delay")
    def test_mark_progress_triggers_certificate_when_course_completed(self, mocked_delay, mocked_log_activity):
        headers = self.auth_header(self.student.username, self.student_password)
        completion_course = TestDataFactory.create_course(
            name="Completion Course",
            instructor=self.instructor,
            category=self.category,
        )
        lesson = TestDataFactory.create_lesson(course=completion_course, order=1, title="Finish Me")
        enrollment = TestDataFactory.create_enrollment(student=self.student, course=completion_course)

        response = self.client.post(
            f"/api/enrollments/{enrollment.id}/progress",
            data=json.dumps({"lesson_id": lesson.id}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["message"], "Lesson marked as complete")
        mocked_delay.assert_called_once_with(self.student.id, completion_course.id)
        mocked_log_activity.assert_called_once()

    @patch("core.apiv1.log_activity")
    @patch("core.apiv1.export_course_report.delay")
    def test_export_report_endpoint_triggers_async_task(self, mocked_delay, mocked_log_activity):
        headers = self.auth_header(self.instructor.username, self.instructor_password)
        response = self.client.post(f"/api/courses/{self.course.id}/export-report", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("Report export started", response.json()["message"])
        mocked_delay.assert_called_once_with(self.course.id)
        mocked_log_activity.assert_called_once()
