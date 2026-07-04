from django.db import IntegrityError
from django.test import TestCase

from courses.models import Certificate, Course, CourseReview, Enrollment, Progress, QuizAttempt, User
from courses.services import ensure_certificate_for_enrollment
from courses.test_factories import TestDataFactory


class CourseModelTests(TestCase):
    def test_course_string_representation_uses_name(self):
        course = TestDataFactory.create_course(name="Django Advanced")
        self.assertEqual(str(course), "Django Advanced")

    def test_course_queryset_for_listing_adds_review_annotations(self):
        instructor = TestDataFactory.create_user(role="instructor")
        course = TestDataFactory.create_course(
            instructor=instructor,
            name="API Engineering",
        )
        student = TestDataFactory.create_user(role="student")
        TestDataFactory.create_lesson(course=course, order=1)
        TestDataFactory.create_enrollment(course=course, student=student)
        TestDataFactory.create_review(course=course, student=student, rating=4)

        listed_course = Course.objects.for_listing().get(id=course.id)

        self.assertEqual(listed_course.lesson_count, 1)
        self.assertEqual(listed_course.student_count, 1)
        self.assertEqual(listed_course.review_count, 1)
        self.assertEqual(round(listed_course.average_rating, 2), 4.0)


class LessonAndProgressModelTests(TestCase):
    def test_progress_sets_completed_at_when_marked_completed(self):
        enrollment = TestDataFactory.create_enrollment()
        lesson = TestDataFactory.create_lesson(course=enrollment.course, order=1)

        progress = Progress.objects.create(
            student=enrollment.student,
            lesson=lesson,
            enrollment=enrollment,
            completed=True,
        )

        self.assertIsNotNone(progress.completed_at)

    def test_progress_unique_constraint_is_enforced(self):
        enrollment = TestDataFactory.create_enrollment()
        lesson = TestDataFactory.create_lesson(course=enrollment.course, order=1)
        TestDataFactory.create_progress(enrollment=enrollment, lesson=lesson)

        with self.assertRaises(IntegrityError):
            Progress.objects.create(
                student=enrollment.student,
                lesson=lesson,
                enrollment=enrollment,
                completed=True,
            )


class EnrollmentAndReviewModelTests(TestCase):
    def test_enrollment_progress_percentage_counts_lesson_and_passed_quiz(self):
        student = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course()
        lesson = TestDataFactory.create_lesson(course=course, order=1)
        quiz = TestDataFactory.create_quiz(course=course, is_published=True)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)
        TestDataFactory.create_progress(
            enrollment=enrollment,
            lesson=lesson,
            student=student,
            completed=True,
        )
        TestDataFactory.create_quiz_attempt(
            quiz=quiz,
            student=student,
            enrollment=enrollment,
            status=QuizAttempt.STATUS_SUBMITTED,
            score=100,
            is_passed=True,
        )

        self.assertEqual(enrollment.progress_percentage(), 100.0)
        self.assertTrue(enrollment.is_course_completed())

    def test_course_review_unique_constraint_is_enforced(self):
        course = TestDataFactory.create_course()
        student = TestDataFactory.create_user(role="student")
        TestDataFactory.create_review(course=course, student=student)

        with self.assertRaises(IntegrityError):
            CourseReview.objects.create(course=course, student=student, rating=5, comment="Duplicate")

    def test_certificate_created_only_when_course_is_completed(self):
        student = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course()
        lesson = TestDataFactory.create_lesson(course=course, order=1)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)

        self.assertIsNone(ensure_certificate_for_enrollment(enrollment))

        TestDataFactory.create_progress(
            enrollment=enrollment,
            lesson=lesson,
            student=student,
            completed=True,
        )

        certificate = ensure_certificate_for_enrollment(enrollment)

        self.assertIsNotNone(certificate)
        self.assertEqual(Certificate.objects.filter(course=course, student=student).count(), 1)


class FixtureDataTests(TestCase):
    fixtures = ["initial_data.json"]

    def test_fixture_loads_curriculum_and_enrollment(self):
        instructor = User.objects.get(username="fixture_instructor")
        student = User.objects.get(username="fixture_student")
        course = Course.objects.get(name="Fixture Django Course")
        enrollment = Enrollment.objects.get(student=student, course=course)
        lesson = course.lessons.get(title="Fixture Intro")

        self.assertEqual(instructor.role, "instructor")
        self.assertEqual(course.status, "published")
        self.assertEqual(course.sections.count(), 1)
        self.assertIsNotNone(lesson.section_id)
        self.assertEqual(str(enrollment), f"{student} -> {course}")
