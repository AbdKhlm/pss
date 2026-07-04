from courses.models import Category, Course, Enrollment, Lesson, Progress, User


class TestDataFactory:
    user_counter = 0
    category_counter = 0
    course_counter = 0
    lesson_counter = 0

    @classmethod
    def create_user(cls, **overrides):
        cls.user_counter += 1
        index = cls.user_counter
        defaults = {
            "username": f"user{index}",
            "email": f"user{index}@example.com",
            "password": "TestPass123!",
            "role": "student",
        }
        defaults.update(overrides)
        password = defaults.pop("password")
        return User.objects.create_user(password=password, **defaults)

    @classmethod
    def create_category(cls, **overrides):
        cls.category_counter += 1
        defaults = {"name": f"Category {cls.category_counter}"}
        defaults.update(overrides)
        return Category.objects.create(**defaults)

    @classmethod
    def create_course(cls, **overrides):
        cls.course_counter += 1
        instructor = overrides.pop("instructor", None)
        category = overrides.pop("category", None)
        defaults = {
            "name": f"Course {cls.course_counter}",
            "description": "Course description",
            "price": 100000,
            "image": "",
            "instructor": instructor or cls.create_user(role="instructor"),
            "category": category or cls.create_category(),
        }
        defaults.update(overrides)
        return Course.objects.create(**defaults)

    @classmethod
    def create_lesson(cls, **overrides):
        cls.lesson_counter += 1
        course = overrides.pop("course", None)
        order = overrides.pop("order", cls.lesson_counter)
        defaults = {
            "course": course or cls.create_course(),
            "title": f"Lesson {cls.lesson_counter}",
            "content": "Lesson content",
            "order": order,
        }
        defaults.update(overrides)
        return Lesson.objects.create(**defaults)

    @classmethod
    def create_enrollment(cls, **overrides):
        student = overrides.pop("student", None)
        course = overrides.pop("course", None)
        defaults = {
            "student": student or cls.create_user(role="student"),
            "course": course or cls.create_course(),
        }
        defaults.update(overrides)
        return Enrollment.objects.create(**defaults)

    @classmethod
    def create_progress(cls, **overrides):
        enrollment = overrides.pop("enrollment", cls.create_enrollment())
        student = overrides.pop("student", None)
        lesson = overrides.pop("lesson", None)
        completed = overrides.pop("completed", True)
        defaults = {
            "student": student or enrollment.student,
            "lesson": lesson or cls.create_lesson(course=enrollment.course, order=1),
            "enrollment": enrollment,
            "completed": completed,
        }
        defaults.update(overrides)
        return Progress.objects.create(**defaults)
