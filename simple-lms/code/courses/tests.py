from django.test import TestCase
from .models import User, Category, Course, Lesson, Enrollment, Progress


class LMSModelTest(TestCase):

    def setUp(self):
        self.instructor = User.objects.create(username='inst1', role='instructor')
        self.student = User.objects.create(username='stud1', role='student')

        self.category = Category.objects.create(name="Programming")

        self.course = Course.objects.create(
            title="Django Basic",
            instructor=self.instructor,
            category=self.category
        )

        self.lesson1 = Lesson.objects.create(course=self.course, title="Intro", order=1)
        self.lesson2 = Lesson.objects.create(course=self.course, title="ORM", order=2)

        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course
        )

    def test_course_creation(self):
        self.assertEqual(self.course.instructor.username, 'inst1')

    def test_lesson_ordering(self):
        lessons = self.course.lessons.all()
        self.assertEqual(lessons[0].order, 1)

    def test_unique_enrollment(self):
        with self.assertRaises(Exception):
            Enrollment.objects.create(
                student=self.student,
                course=self.course
            )

    def test_progress_tracking(self):
        Progress.objects.create(
            student=self.student,
            lesson=self.lesson1,
            enrollment=self.enrollment,
            completed=True
        )

        self.assertEqual(self.enrollment.progress_percentage(), 50.0)

    def test_queryset_optimization(self):
        qs = Course.objects.for_listing()
        self.assertTrue(qs.exists())