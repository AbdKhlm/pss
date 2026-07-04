import json
from typing import Any, cast
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from django.core.cache import cache
from django.conf import settings
from django.test import TestCase
from ninja.errors import HttpError

from core.apiv1 import rate_limit
from core.mongo import (
    ACTIVITY_LOGS_COLLECTION,
    LEARNING_ANALYTICS_COLLECTION,
    build_activity_document,
    delete_activity_logs,
    get_learning_analytics,
    list_activity_logs,
    log_activity,
    record_daily_login,
    sync_learning_analytics,
    update_activity_logs,
)
from core.tasks import (
    add_numbers,
    export_course_report,
    generate_certificate,
    send_enrollment_email,
    update_course_statistics,
)
from core.utils import get_user_role, is_admin, is_instructor, is_student
from courses.models import Course, User
from courses.test_factories import TestDataFactory


class RoleDecoratorTests(TestCase):
    def _request_for_role(self, role, authenticated=True, is_superuser=False, is_staff=False):
        return SimpleNamespace(
            user=SimpleNamespace(
                is_authenticated=authenticated,
                role=role,
                is_superuser=is_superuser,
                is_staff=is_staff,
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

    def test_get_user_role_maps_superuser_without_role_to_admin(self):
        user = SimpleNamespace(role="", is_superuser=True, is_staff=True)

        self.assertEqual(get_user_role(user), "admin")

    def test_is_student_allows_superuser_with_blank_role(self):
        @is_student
        def protected_view(request):
            return "ok"

        response = protected_view(self._request_for_role("", is_superuser=True, is_staff=True))

        self.assertEqual(response, "ok")


class MongoHelperTests(TestCase):
    def _mock_db(self):
        db = MagicMock()
        activity_collection = MagicMock()
        analytics_collection = MagicMock()
        db.__getitem__.side_effect = lambda key: {
            ACTIVITY_LOGS_COLLECTION: activity_collection,
            LEARNING_ANALYTICS_COLLECTION: analytics_collection,
        }[key]
        return db, activity_collection, analytics_collection

    def test_build_activity_document_embeds_snapshots(self):
        user = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course(instructor=TestDataFactory.create_user(role="instructor"))
        lesson = TestDataFactory.create_lesson(course=course, order=1)

        document = build_activity_document(
            user_id=user.id,
            user_role=user.role,
            action="LESSON_COMPLETE",
            user=user,
            course=course,
            lesson=lesson,
            metadata={"browser": "Chrome"},
        )

        self.assertEqual(document["user_snapshot"]["username"], user.username)
        self.assertEqual(document["course_snapshot"]["name"], course.name)
        self.assertEqual(document["lesson_snapshot"]["title"], lesson.title)
        self.assertIsNotNone(document["created_at"])

    def test_log_activity_inserts_expected_document(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.insert_one.return_value.inserted_id = "mongo-id"

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
        inserted_document = activity_collection.insert_one.call_args.args[0]
        self.assertEqual(inserted_document["user_id"], 10)
        self.assertEqual(inserted_document["action"], "TEST_ACTION")
        self.assertEqual(inserted_document["metadata"]["source"], "test")
        self.assertIsNotNone(inserted_document["created_at"])

    def test_get_learning_analytics_builds_match_stage_when_course_filter_is_given(self):
        db, activity_collection, analytics_collection = self._mock_db()
        analytics_collection.find.return_value.sort.return_value = []
        activity_collection.aggregate.return_value = [
            {"course_id": 1, "total_actions": 4, "unique_user_count": 2, "action_type_count": 1}
        ]

        with patch("core.mongo.get_mongo_db", return_value=db):
            result = get_learning_analytics(course_id=1)

        pipeline = activity_collection.aggregate.call_args.args[0]
        first_result = cast(dict[str, Any], result[0])
        self.assertEqual(pipeline[0], {"$match": {"course_id": 1}})
        self.assertEqual(first_result["total_actions"], 4)

    def test_get_mongo_db_uses_configured_connection_settings(self):
        fake_client = MagicMock()

        with patch("core.mongo.MongoClient", return_value=fake_client) as mocked_client:
            from core.mongo import get_mongo_db

            db = get_mongo_db()

        mocked_client.assert_called_once_with(settings.MONGODB_URI)
        self.assertIs(db, fake_client.__getitem__.return_value)

    def test_list_activity_logs_reads_from_mongo_with_sort_and_limit(self):
        db, activity_collection, _ = self._mock_db()
        cursor = MagicMock()
        cursor.sort.return_value.skip.return_value.limit.return_value = [
            {"_id": "mongo-1", "action": "COURSE_VIEW", "created_at": "2026-07-04T00:00:00"}
        ]
        activity_collection.find.return_value = cursor

        with patch("core.mongo.get_mongo_db", return_value=db):
            logs = list_activity_logs(filters={"action": "COURSE_VIEW"}, limit=5, skip=10)

        activity_collection.find.assert_called_once_with({"action": "COURSE_VIEW"})
        first_log = cast(dict[str, Any], logs[0])
        self.assertEqual(first_log["action"], "COURSE_VIEW")

    def test_update_activity_logs_uses_set_operator(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.update_many.return_value = SimpleNamespace(
            matched_count=3,
            modified_count=2,
            upserted_id=None,
        )

        with patch("core.mongo.get_mongo_db", return_value=db):
            result = update_activity_logs(
                filters={"action": "COURSE_VIEW"},
                updates={"reviewed": True},
            )

        activity_collection.update_many.assert_called_once_with(
            {"action": "COURSE_VIEW"},
            {"$set": {"reviewed": True}},
            upsert=False,
        )
        self.assertEqual(result["modified_count"], 2)

    def test_delete_activity_logs_returns_deleted_count(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.delete_many.return_value.deleted_count = 4

        with patch("core.mongo.get_mongo_db", return_value=db):
            deleted_count = delete_activity_logs(filters={"action": "TEST"})

        self.assertEqual(deleted_count, 4)

    def test_record_daily_login_uses_upsert_and_increment(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.update_one.return_value = SimpleNamespace(
            matched_count=0,
            modified_count=0,
            upserted_id="login-id",
        )

        with patch("core.mongo.get_mongo_db", return_value=db):
            result = record_daily_login(user_id=1)

        self.assertEqual(result["upserted_id"], "login-id")
        _, kwargs = activity_collection.update_one.call_args
        self.assertTrue(kwargs["upsert"])

    def test_sync_learning_analytics_persists_aggregated_documents(self):
        db, _, analytics_collection = self._mock_db()

        with patch(
            "core.mongo.aggregate_learning_analytics",
            return_value=[
                {
                    "course_id": 1,
                    "course_name": "Django API",
                    "total_actions": 5,
                    "unique_user_count": 2,
                    "action_type_count": 3,
                    "last_activity_at": "2026-07-04T12:00:00",
                }
            ],
        ), patch("core.mongo.get_mongo_db", return_value=db):
            result = sync_learning_analytics()

        analytics_collection.replace_one.assert_called_once()
        self.assertEqual(result["synced_count"], 1)


class CeleryTaskTests(TestCase):
    def test_add_numbers_returns_sum_payload(self):
        result = add_numbers(4, 6)

        self.assertEqual(result["operation"], "add_numbers")
        self.assertEqual(result["result"], 10)

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
    def test_login_endpoint_returns_access_and_refresh_tokens(self, mocked_log_activity):
        response = self.client.post(
            "/api/auth/login",
            data=json.dumps(
                {
                    "username": self.student.username,
                    "password": self.student_password,
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertTrue(payload["access"])
        self.assertTrue(payload["refresh"])
        mocked_log_activity.assert_called_once()

    def test_superuser_with_blank_role_can_enroll(self):
        admin_like_user = TestDataFactory.create_user(
            username="legacy_admin",
            email="legacy_admin@example.com",
            password="LegacyAdmin123!",
            role="",
        )
        admin_like_user.is_staff = True
        admin_like_user.is_superuser = True
        admin_like_user.save(update_fields=["is_staff", "is_superuser"])

        login_response = self.client.post(
            "/api/auth/login",
            data=json.dumps(
                {
                    "username": "legacy_admin",
                    "password": "LegacyAdmin123!",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)
        access_token = login_response.json()["access"]
        headers = {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

        with patch("core.apiv1.log_activity"), patch("core.apiv1.send_enrollment_email.delay"):
            response = self.client.post(
                "/api/enrollments",
                data=json.dumps({"course_id": self.course.id}),
                content_type="application/json",
                **headers,
            )

        self.assertEqual(response.status_code, 201, response.content)

    def test_swagger_style_authorization_with_quoted_access_token_is_accepted(self):
        login_response = self.client.post(
            "/api/auth/login",
            data=json.dumps(
                {
                    "username": self.student.username,
                    "password": self.student_password,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)
        access_token = login_response.json()["access"]
        headers = {"HTTP_AUTHORIZATION": f'Bearer "{access_token}"'}

        with patch("core.apiv1.log_activity"):
            response = self.client.get("/api/auth/me", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["username"], self.student.username)

    @patch("core.apiv1.list_activity_logs")
    def test_admin_can_get_activity_logs(self, mocked_list_activity_logs):
        mocked_list_activity_logs.return_value = [
            {
                "_id": "mongo-1",
                "user_id": self.student.id,
                "user_role": "student",
                "action": "COURSE_VIEW",
                "course_id": self.course.id,
                "lesson_id": None,
                "metadata": {"browser": "Chrome"},
                "user_snapshot": None,
                "course_snapshot": None,
                "lesson_snapshot": None,
                "created_at": "2026-07-04T00:00:00",
            }
        ]
        headers = self.auth_header(self.admin.username, self.admin_password)

        response = self.client.get("/api/analytics/activity-logs", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()[0]["id"], "mongo-1")

    @patch("core.apiv1.get_learning_analytics")
    def test_instructor_learning_analytics_is_filtered_to_owned_courses(self, mocked_get_learning_analytics):
        other_instructor = TestDataFactory.create_user(role="instructor", username="other_teacher")
        other_course = TestDataFactory.create_course(
            instructor=other_instructor,
            category=self.category,
            name="Other Course",
        )
        mocked_get_learning_analytics.return_value = [
            {
                "course_id": self.course.id,
                "course_name": self.course.name,
                "total_actions": 5,
                "unique_user_count": 2,
                "action_type_count": 3,
                "last_activity_at": "2026-07-04T00:00:00",
            },
            {
                "course_id": other_course.id,
                "course_name": other_course.name,
                "total_actions": 8,
                "unique_user_count": 4,
                "action_type_count": 2,
                "last_activity_at": "2026-07-04T00:00:00",
            },
        ]
        headers = self.auth_header(self.instructor.username, self.instructor_password)

        response = self.client.get("/api/analytics/learning", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["course_id"], self.course.id)

    @patch("core.apiv1.sync_learning_analytics")
    def test_admin_can_rebuild_learning_analytics(self, mocked_sync_learning_analytics):
        mocked_sync_learning_analytics.return_value = {"synced_count": 2, "course_id": None}
        headers = self.auth_header(self.admin.username, self.admin_password)

        response = self.client.post("/api/analytics/learning/rebuild", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["synced_count"], 2)

    @patch("core.apiv1.log_activity")
    def test_authenticated_user_can_queue_demo_add_task(self, mocked_log_activity):
        headers = self.auth_header(self.student.username, self.student_password)

        response = self.client.post(
            "/api/tasks/demo-add",
            data=json.dumps({"x": 4, "y": 5, "countdown": 0}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["message"], "Task queued successfully")
        self.assertTrue(response.json()["task_id"])
        mocked_log_activity.assert_called_once()

    def test_authenticated_user_can_check_task_status(self):
        headers = self.auth_header(self.student.username, self.student_password)
        queued_task = add_numbers.delay(7, 8)

        response = self.client.get(f"/api/tasks/{queued_task.id}", **headers)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "SUCCESS")
        self.assertEqual(response.json()["result"]["result"], 15)

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
    @patch("core.apiv1.send_enrollment_email.delay")
    def test_enroll_endpoint_returns_existing_enrollment_with_200_when_already_enrolled(self, mocked_delay, mocked_log_activity):
        headers = self.auth_header(self.student.username, self.student_password)
        existing_course = TestDataFactory.create_course(
            name="Existing Enrollment Course",
            instructor=self.instructor,
            category=self.category,
        )
        existing_enrollment = TestDataFactory.create_enrollment(
            student=self.student,
            course=existing_course,
        )

        response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": existing_course.id}),
            content_type="application/json",
            **headers,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["id"], existing_enrollment.id)
        self.assertEqual(
            existing_course.enrollments.filter(student=self.student).count(),
            1,
        )
        mocked_delay.assert_not_called()
        mocked_log_activity.assert_not_called()

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
