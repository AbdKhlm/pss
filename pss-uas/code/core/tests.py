import json
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.cache import cache
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
from core.tasks import add_numbers, export_course_report, generate_certificate, send_enrollment_email
from core.utils import get_user_role, is_admin, is_instructor, is_student
from courses.models import Course, QuizAttempt, User
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

    def test_update_and_delete_activity_logs_return_counts(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.update_many.return_value = SimpleNamespace(
            matched_count=3,
            modified_count=2,
            upserted_id=None,
        )
        activity_collection.delete_many.return_value.deleted_count = 4

        with patch("core.mongo.get_mongo_db", return_value=db):
            updated = update_activity_logs(filters={"action": "COURSE_VIEW"}, updates={"reviewed": True})
            deleted = delete_activity_logs(filters={"action": "TEST"})

        self.assertEqual(updated["modified_count"], 2)
        self.assertEqual(deleted, 4)

    def test_record_daily_login_uses_upsert(self):
        db, activity_collection, _ = self._mock_db()
        activity_collection.update_one.return_value = SimpleNamespace(
            matched_count=0,
            modified_count=0,
            upserted_id="login-id",
        )

        with patch("core.mongo.get_mongo_db", return_value=db):
            result = record_daily_login(user_id=1)

        self.assertEqual(result["upserted_id"], "login-id")

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

    def test_generate_certificate_returns_done_when_course_is_completed(self):
        student = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course()
        lesson = TestDataFactory.create_lesson(course=course, order=1)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)
        TestDataFactory.create_progress(enrollment=enrollment, student=student, lesson=lesson, completed=True)

        result = generate_certificate(student.id, course.id)

        self.assertEqual(result["status"], "done")
        self.assertTrue(result["certificate_code"])

    def test_export_course_report_generates_csv_content(self):
        student = TestDataFactory.create_user(role="student", username="csvstudent")
        course = TestDataFactory.create_course(name="CSV Course")
        lesson = TestDataFactory.create_lesson(course=course, order=1)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)
        TestDataFactory.create_progress(enrollment=enrollment, student=student, lesson=lesson, completed=True)

        report = export_course_report(course.id)

        self.assertIn("Student Username", report)
        self.assertIn("csvstudent", report)


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
        self.log_activity_patcher = patch("core.apiv1.log_activity", return_value="mongo-id")
        self.send_mail_patcher = patch("core.apiv1.send_enrollment_email.delay")
        self.generate_certificate_patcher = patch("core.apiv1.generate_certificate.delay")
        self.log_activity_patcher.start()
        self.mock_send_mail = self.send_mail_patcher.start()
        self.mock_generate_certificate = self.generate_certificate_patcher.start()
        self.addCleanup(self.log_activity_patcher.stop)
        self.addCleanup(self.send_mail_patcher.stop)
        self.addCleanup(self.generate_certificate_patcher.stop)

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
            level="beginner",
            status="published",
        )
        self.section = TestDataFactory.create_section(course=self.course, order=1, title="Module 1")
        self.lesson = TestDataFactory.create_lesson(
            course=self.course,
            section=self.section,
            order=1,
            title="Intro API",
        )

    def auth_header(self, username, password):
        response = self.client.post(
            "/api/auth/login",
            data=json.dumps({"username": username, "password": password}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        token = response.json()["access"]
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_register_login_and_me_flow(self):
        register_response = self.client.post(
            "/api/auth/register",
            data=json.dumps(
                {
                    "username": "newstudent",
                    "first_name": "New",
                    "last_name": "Student",
                    "email": "newstudent@example.com",
                    "password": "NewStudent123!",
                    "role": "admin",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(register_response.status_code, 200, register_response.content)
        self.assertEqual(register_response.json()["role"], "student")

        headers = self.auth_header("newstudent", "NewStudent123!")
        me_response = self.client.get("/api/auth/me", **headers)
        self.assertEqual(me_response.status_code, 200, me_response.content)
        self.assertEqual(me_response.json()["username"], "newstudent")

    def test_course_discovery_hides_draft_course_from_public(self):
        TestDataFactory.create_course(
            name="Draft Course",
            instructor=self.instructor,
            category=self.category,
            status="draft",
        )

        response = self.client.get("/api/courses", {"search": "Course"})

        self.assertEqual(response.status_code, 200, response.content)
        names = [item["name"] for item in response.json()]
        self.assertIn("Django API", names)
        self.assertNotIn("Draft Course", names)

    def test_course_discovery_supports_advanced_filters_and_sorting(self):
        other_instructor = TestDataFactory.create_user(role="instructor", username="mentor_api")
        frontend_category = TestDataFactory.create_category(name="Frontend")
        advanced_course = TestDataFactory.create_course(
            name="Advanced Django",
            instructor=self.instructor,
            category=self.category,
            level="advanced",
            status="published",
            price=250000,
        )
        frontend_course = TestDataFactory.create_course(
            name="React Fundamentals",
            instructor=other_instructor,
            category=frontend_category,
            level="beginner",
            status="published",
            price=50000,
        )
        draft_course = TestDataFactory.create_course(
            name="Hidden Draft",
            instructor=other_instructor,
            category=frontend_category,
            level="intermediate",
            status="draft",
        )

        popular_student = TestDataFactory.create_user(role="student", username="popular_student")
        secondary_student = TestDataFactory.create_user(role="student", username="secondary_student")
        TestDataFactory.create_enrollment(student=popular_student, course=advanced_course)
        TestDataFactory.create_enrollment(student=secondary_student, course=advanced_course)
        TestDataFactory.create_enrollment(student=popular_student, course=frontend_course)
        TestDataFactory.create_review(course=advanced_course, student=popular_student, rating=5)
        TestDataFactory.create_review(course=frontend_course, student=secondary_student, rating=3)

        response = self.client.get(
            "/api/courses",
            {
                "search": "Django",
                "category_id": self.category.id,
                "instructor_id": self.instructor.id,
                "level": "advanced",
                "sort": "rating",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["name"] for item in response.json()], ["Advanced Django"])

        popular_response = self.client.get("/api/courses", {"sort": "popular"})
        self.assertEqual(popular_response.status_code, 200, popular_response.content)
        self.assertEqual(popular_response.json()[0]["name"], "Advanced Django")

        admin_headers = self.auth_header(self.admin.username, self.admin_password)
        draft_response = self.client.get(
            "/api/courses",
            {"status": "draft", "instructor_id": other_instructor.id},
            **admin_headers,
        )
        self.assertEqual(draft_response.status_code, 200, draft_response.content)
        self.assertEqual([item["name"] for item in draft_response.json()], ["Hidden Draft"])
        self.assertEqual(draft_response.json()[0]["status"], "draft")

    def test_instructor_can_build_curriculum(self):
        headers = self.auth_header(self.instructor.username, self.instructor_password)

        section_response = self.client.post(
            f"/api/courses/{self.course.id}/sections",
            data=json.dumps({"title": "Module 2", "description": "Advanced", "order": 2}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(section_response.status_code, 200, section_response.content)

        new_section = self.course.sections.get(title="Module 2")
        lesson_response = self.client.post(
            f"/api/courses/{self.course.id}/lessons",
            data=json.dumps(
                {
                    "section_id": new_section.id,
                    "title": "Advanced API",
                    "content": "Lesson body",
                    "order": 2,
                }
            ),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(lesson_response.status_code, 200, lesson_response.content)
        self.assertTrue(self.course.lessons.filter(title="Advanced API").exists())

    def test_student_review_wishlist_and_dashboard_flow(self):
        headers = self.auth_header(self.student.username, self.student_password)

        enroll_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": self.course.id}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(enroll_response.status_code, 201, enroll_response.content)

        review_response = self.client.post(
            f"/api/courses/{self.course.id}/reviews",
            data=json.dumps({"rating": 5, "comment": "Mantap"}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(review_response.status_code, 200, review_response.content)

        wishlist_response = self.client.post(
            "/api/wishlist",
            data=json.dumps({"course_id": self.course.id}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(wishlist_response.status_code, 200, wishlist_response.content)

        dashboard_response = self.client.get("/api/dashboard/student", **headers)
        self.assertEqual(dashboard_response.status_code, 200, dashboard_response.content)
        self.assertEqual(len(dashboard_response.json()["active_courses"]), 1)
        self.assertEqual(len(dashboard_response.json()["wishlist_courses"]), 1)

    def test_quiz_submission_generates_certificate_and_leaderboard_entry(self):
        instructor_headers = self.auth_header(self.instructor.username, self.instructor_password)
        student_headers = self.auth_header(self.student.username, self.student_password)

        enroll_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": self.course.id}),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(enroll_response.status_code, 201, enroll_response.content)
        enrollment_id = enroll_response.json()["id"]

        quiz_response = self.client.post(
            f"/api/courses/{self.course.id}/quizzes",
            data=json.dumps(
                {
                    "title": "Quiz Intro",
                    "description": "Basic quiz",
                    "instructions": "Pilih jawaban benar",
                    "lesson_id": self.lesson.id,
                    "passing_grade": 70,
                    "attempt_limit": 2,
                    "shuffle_questions": False,
                    "shuffle_options": False,
                    "is_published": True,
                    "questions": [
                        {
                            "prompt": "HTTP kepanjangan dari?",
                            "weight": 10,
                            "options": [
                                {"text": "HyperText Transfer Protocol", "is_correct": True},
                                {"text": "High Transfer Text Process", "is_correct": False},
                            ],
                        }
                    ],
                }
            ),
            content_type="application/json",
            **instructor_headers,
        )
        self.assertEqual(quiz_response.status_code, 201, quiz_response.content)
        quiz_id = quiz_response.json()["id"]
        correct_option_id = quiz_response.json()["questions"][0]["options"][0]["id"]

        progress_response = self.client.post(
            f"/api/enrollments/{enrollment_id}/progress",
            data=json.dumps({"lesson_id": self.lesson.id}),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(progress_response.status_code, 200, progress_response.content)

        start_response = self.client.post(f"/api/quizzes/{quiz_id}/attempts/start", **student_headers)
        self.assertEqual(start_response.status_code, 200, start_response.content)
        attempt_id = start_response.json()["attempt_id"]

        submit_response = self.client.post(
            f"/api/quiz-attempts/{attempt_id}/submit",
            data=json.dumps(
                {
                    "answers": [
                        {
                            "question_id": start_response.json()["questions"][0]["id"],
                            "selected_option_id": correct_option_id,
                        }
                    ]
                }
            ),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.content)
        self.assertTrue(submit_response.json()["is_passed"])
        self.assertTrue(submit_response.json()["certificate_code"])

        verify_response = self.client.get(
            f"/api/certificates/verify/{submit_response.json()['certificate_code']}"
        )
        self.assertEqual(verify_response.status_code, 200, verify_response.content)
        self.assertTrue(verify_response.json()["is_valid"])

        leaderboard_response = self.client.get(f"/api/courses/{self.course.id}/leaderboard")
        self.assertEqual(leaderboard_response.status_code, 200, leaderboard_response.content)
        self.assertEqual(leaderboard_response.json()[0]["student_id"], self.student.id)

    def test_certificate_pdf_endpoint_returns_pdf_attachment(self):
        instructor_headers = self.auth_header(self.instructor.username, self.instructor_password)
        student_headers = self.auth_header(self.student.username, self.student_password)

        enroll_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": self.course.id}),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(enroll_response.status_code, 201, enroll_response.content)
        enrollment_id = enroll_response.json()["id"]

        quiz_response = self.client.post(
            f"/api/courses/{self.course.id}/quizzes",
            data=json.dumps(
                {
                    "title": "Certificate Quiz",
                    "description": "Quiz for certificate PDF",
                    "instructions": "Jawab benar",
                    "lesson_id": self.lesson.id,
                    "passing_grade": 70,
                    "attempt_limit": 2,
                    "shuffle_questions": False,
                    "shuffle_options": False,
                    "is_published": True,
                    "questions": [
                        {
                            "prompt": "REST singkatan dari?",
                            "weight": 10,
                            "options": [
                                {"text": "Representational State Transfer", "is_correct": True},
                                {"text": "Remote State Task", "is_correct": False},
                            ],
                        }
                    ],
                }
            ),
            content_type="application/json",
            **instructor_headers,
        )
        self.assertEqual(quiz_response.status_code, 201, quiz_response.content)

        progress_response = self.client.post(
            f"/api/enrollments/{enrollment_id}/progress",
            data=json.dumps({"lesson_id": self.lesson.id}),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(progress_response.status_code, 200, progress_response.content)

        start_response = self.client.post(
            f"/api/quizzes/{quiz_response.json()['id']}/attempts/start",
            **student_headers,
        )
        self.assertEqual(start_response.status_code, 200, start_response.content)

        submit_response = self.client.post(
            f"/api/quiz-attempts/{start_response.json()['attempt_id']}/submit",
            data=json.dumps(
                {
                    "answers": [
                        {
                            "question_id": start_response.json()["questions"][0]["id"],
                            "selected_option_id": quiz_response.json()["questions"][0]["options"][0]["id"],
                        }
                    ]
                }
            ),
            content_type="application/json",
            **student_headers,
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.content)
        certificate_code = submit_response.json()["certificate_code"]
        self.assertIsNotNone(certificate_code)

        pdf_response = self.client.get(
            f"/api/certificates/{certificate_code}/pdf",
            **student_headers,
        )
        self.assertEqual(pdf_response.status_code, 200, pdf_response.content)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertIn(f'certificate-{certificate_code}.pdf', pdf_response["Content-Disposition"])
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    @patch("courses.services.random.shuffle", side_effect=lambda sequence: sequence.reverse())
    def test_quiz_attempt_start_randomizes_question_and_option_order(self, mocked_shuffle):
        instructor_headers = self.auth_header(self.instructor.username, self.instructor_password)
        student_headers = self.auth_header(self.student.username, self.student_password)
        TestDataFactory.create_enrollment(student=self.student, course=self.course)

        quiz_response = self.client.post(
            f"/api/courses/{self.course.id}/quizzes",
            data=json.dumps(
                {
                    "title": "Random Quiz",
                    "description": "Quiz with randomized order",
                    "instructions": "Perhatikan urutan",
                    "lesson_id": self.lesson.id,
                    "passing_grade": 70,
                    "attempt_limit": 2,
                    "shuffle_questions": True,
                    "shuffle_options": True,
                    "is_published": True,
                    "questions": [
                        {
                            "prompt": "Question A",
                            "weight": 5,
                            "order": 1,
                            "options": [
                                {"text": "A1", "is_correct": True, "order": 1},
                                {"text": "A2", "is_correct": False, "order": 2},
                            ],
                        },
                        {
                            "prompt": "Question B",
                            "weight": 5,
                            "order": 2,
                            "options": [
                                {"text": "B1", "is_correct": True, "order": 1},
                                {"text": "B2", "is_correct": False, "order": 2},
                            ],
                        },
                    ],
                }
            ),
            content_type="application/json",
            **instructor_headers,
        )
        self.assertEqual(quiz_response.status_code, 201, quiz_response.content)

        original_question_ids = [question["id"] for question in quiz_response.json()["questions"]]
        original_option_ids = {
            question["id"]: [option["id"] for option in question["options"]]
            for question in quiz_response.json()["questions"]
        }

        start_response = self.client.post(
            f"/api/quizzes/{quiz_response.json()['id']}/attempts/start",
            **student_headers,
        )
        self.assertEqual(start_response.status_code, 200, start_response.content)

        randomized_question_ids = [question["id"] for question in start_response.json()["questions"]]
        self.assertEqual(randomized_question_ids, list(reversed(original_question_ids)))

        for question in start_response.json()["questions"]:
            self.assertEqual(
                [option["id"] for option in question["options"]],
                list(reversed(original_option_ids[question["id"]])),
            )

        self.assertGreaterEqual(mocked_shuffle.call_count, 3)

    def test_progress_detail_endpoint_returns_section_and_quiz_summary(self):
        headers = self.auth_header(self.student.username, self.student_password)
        quiz = TestDataFactory.create_quiz(course=self.course, lesson=self.lesson, is_published=True)
        TestDataFactory.create_question(quiz=quiz, order=1)

        enroll_response = self.client.post(
            "/api/enrollments",
            data=json.dumps({"course_id": self.course.id}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(enroll_response.status_code, 201, enroll_response.content)
        enrollment_id = enroll_response.json()["id"]

        progress_response = self.client.get(f"/api/enrollments/{enrollment_id}/progress", **headers)
        self.assertEqual(progress_response.status_code, 200, progress_response.content)
        self.assertEqual(progress_response.json()["total_lessons"], 1)
        self.assertEqual(progress_response.json()["total_quizzes"], 1)
        self.assertEqual(len(progress_response.json()["sections"]), 1)

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
                "metadata": {},
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

    def test_authenticated_user_can_queue_demo_add_task_and_read_status(self):
        headers = self.auth_header(self.student.username, self.student_password)

        queue_response = self.client.post(
            "/api/tasks/demo-add",
            data=json.dumps({"x": 7, "y": 8, "countdown": 0}),
            content_type="application/json",
            **headers,
        )
        self.assertEqual(queue_response.status_code, 200, queue_response.content)

        task_id = queue_response.json()["task_id"]
        status_response = self.client.get(f"/api/tasks/{task_id}", **headers)
        self.assertEqual(status_response.status_code, 200, status_response.content)
        self.assertEqual(status_response.json()["result"]["result"], 15)
