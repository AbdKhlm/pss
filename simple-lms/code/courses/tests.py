from django.db import IntegrityError
from django.test import TestCase

from courses.models import Course, Enrollment, Lesson, Progress, User
from courses.test_factories import TestDataFactory


class CourseModelTests(TestCase):
    def test_course_string_representation_uses_name(self):
        course = TestDataFactory.create_course(name="Django Advanced")
        self.assertEqual(str(course), "Django Advanced")

    def test_course_queryset_for_listing_adds_annotations(self):
        instructor = TestDataFactory.create_user(role="instructor")
        category = TestDataFactory.create_category(name="Backend")
        course = TestDataFactory.create_course(
            instructor=instructor,
            category=category,
            name="API Engineering",
        )
        TestDataFactory.create_lesson(course=course, order=1)
        TestDataFactory.create_lesson(course=course, order=2)
        TestDataFactory.create_enrollment(course=course)

        listed_course = Course.objects.for_listing().get(id=course.id)

        self.assertEqual(listed_course.lesson_count, 2)
        self.assertEqual(listed_course.student_count, 1)


class LessonAndProgressModelTests(TestCase):
    def test_lesson_ordering_is_ascending_by_order(self):
        course = TestDataFactory.create_course()
        lesson_two = TestDataFactory.create_lesson(course=course, order=2, title="Second")
        lesson_one = TestDataFactory.create_lesson(course=course, order=1, title="First")

        self.assertEqual(list(course.lessons.all()), [lesson_one, lesson_two])

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


class EnrollmentModelTests(TestCase):
    def test_enrollment_unique_constraint_is_enforced(self):
        student = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course()
        TestDataFactory.create_enrollment(student=student, course=course)

        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(student=student, course=course)

    def test_progress_percentage_counts_completed_lessons(self):
        student = TestDataFactory.create_user(role="student")
        course = TestDataFactory.create_course()
        lesson_one = TestDataFactory.create_lesson(course=course, order=1)
        TestDataFactory.create_lesson(course=course, order=2)
        enrollment = TestDataFactory.create_enrollment(student=student, course=course)
        TestDataFactory.create_progress(
            enrollment=enrollment,
            lesson=lesson_one,
            student=student,
            completed=True,
        )

        self.assertEqual(enrollment.progress_percentage(), 50.0)


class FixtureDataTests(TestCase):
    fixtures = ["initial_data.json"]

    def test_fixture_loads_core_lms_data(self):
        instructor = User.objects.get(username="fixture_instructor")
        student = User.objects.get(username="fixture_student")
        course = Course.objects.get(name="Fixture Django Course")
        enrollment = Enrollment.objects.get(student=student, course=course)

        self.assertEqual(instructor.role, "instructor")
        self.assertEqual(course.lessons.count(), 2)
        self.assertEqual(str(enrollment), f"{student} -> {course}")
