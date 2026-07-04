from courses.models import (
    Category,
    Course,
    CourseReview,
    CourseSection,
    CourseWishlist,
    Enrollment,
    Lesson,
    Progress,
    Quiz,
    QuizAttempt,
    QuizOption,
    QuizQuestion,
    User,
)


class TestDataFactory:
    user_counter = 0
    category_counter = 0
    course_counter = 0
    section_counter = 0
    lesson_counter = 0
    quiz_counter = 0
    question_counter = 0

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
            "level": Course.LEVEL_BEGINNER,
            "status": Course.STATUS_PUBLISHED,
            "instructor": instructor or cls.create_user(role="instructor"),
            "category": category or cls.create_category(),
        }
        defaults.update(overrides)
        return Course.objects.create(**defaults)

    @classmethod
    def create_section(cls, **overrides):
        cls.section_counter += 1
        course = overrides.pop("course", None)
        defaults = {
            "course": course or cls.create_course(),
            "title": f"Section {cls.section_counter}",
            "description": "Section description",
            "order": cls.section_counter,
        }
        defaults.update(overrides)
        return CourseSection.objects.create(**defaults)

    @classmethod
    def create_lesson(cls, **overrides):
        cls.lesson_counter += 1
        course = overrides.pop("course", None)
        section = overrides.pop("section", None)
        order = overrides.pop("order", cls.lesson_counter)
        selected_course = course or cls.create_course()
        selected_section = section or cls.create_section(course=selected_course, order=order)
        defaults = {
            "course": selected_course,
            "section": selected_section,
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

    @classmethod
    def create_review(cls, **overrides):
        course = overrides.pop("course", None) or cls.create_course()
        student = overrides.pop("student", None) or cls.create_user(role="student")
        defaults = {
            "course": course,
            "student": student,
            "rating": 5,
            "comment": "Excellent course",
        }
        defaults.update(overrides)
        return CourseReview.objects.create(**defaults)

    @classmethod
    def create_wishlist(cls, **overrides):
        course = overrides.pop("course", None) or cls.create_course()
        student = overrides.pop("student", None) or cls.create_user(role="student")
        defaults = {
            "course": course,
            "student": student,
        }
        defaults.update(overrides)
        return CourseWishlist.objects.create(**defaults)

    @classmethod
    def create_quiz(cls, **overrides):
        cls.quiz_counter += 1
        course = overrides.pop("course", None) or cls.create_course()
        defaults = {
            "course": course,
            "lesson": overrides.pop("lesson", None),
            "title": f"Quiz {cls.quiz_counter}",
            "description": "Quiz description",
            "passing_grade": 70,
            "attempt_limit": 3,
            "shuffle_questions": True,
            "shuffle_options": True,
            "is_published": True,
        }
        defaults.update(overrides)
        return Quiz.objects.create(**defaults)

    @classmethod
    def create_question(cls, **overrides):
        cls.question_counter += 1
        quiz = overrides.pop("quiz", None) or cls.create_quiz()
        skip_default_options = overrides.pop("skip_default_options", False)
        defaults = {
            "quiz": quiz,
            "prompt": f"Question {cls.question_counter}",
            "explanation": "",
            "weight": 1,
            "order": cls.question_counter,
        }
        defaults.update(overrides)
        question = QuizQuestion.objects.create(**defaults)
        if not skip_default_options:
            cls.create_option(question=question, text="Correct", is_correct=True, order=1)
            cls.create_option(question=question, text="Incorrect", is_correct=False, order=2)
        return question

    @classmethod
    def create_option(cls, **overrides):
        question = overrides.pop("question", None) or cls.create_question(skip_default_options=True)
        defaults = {
            "question": question,
            "text": "Option",
            "is_correct": False,
            "order": 1,
        }
        defaults.update(overrides)
        return QuizOption.objects.create(**defaults)

    @classmethod
    def create_quiz_attempt(cls, **overrides):
        quiz = overrides.pop("quiz", None) or cls.create_quiz()
        student = overrides.pop("student", None) or cls.create_user(role="student")
        enrollment = overrides.pop("enrollment", None) or cls.create_enrollment(student=student, course=quiz.course)
        defaults = {
            "quiz": quiz,
            "student": student,
            "enrollment": enrollment,
            "status": QuizAttempt.STATUS_SUBMITTED,
            "question_order": [],
            "option_order": {},
            "total_points": 10,
            "earned_points": 10,
            "score": 100,
            "is_passed": True,
        }
        defaults.update(overrides)
        return QuizAttempt.objects.create(**defaults)
