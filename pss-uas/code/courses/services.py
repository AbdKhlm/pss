import random
import secrets
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone
from ninja.errors import HttpError

from courses.models import (
    Certificate,
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
    StudentAnswer,
)
from core.utils import get_user_role


def to_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def annotate_courses(queryset):
    return (
        queryset.select_related("instructor", "category")
        .annotate(
            lesson_count=Count("lessons", distinct=True),
            student_count=Count("enrollments", distinct=True),
            review_count=Count("reviews", distinct=True),
            average_rating=Avg("reviews__rating"),
            wishlist_count=Count("wishlists", distinct=True),
        )
    )


def can_manage_course(user, course: Course) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if get_user_role(user) == "admin":
        return True
    return course.instructor_id == user.id


def can_view_course(user, course: Course) -> bool:
    if course.status == Course.STATUS_PUBLISHED:
        return True
    if not getattr(user, "is_authenticated", False):
        return False
    if can_manage_course(user, course):
        return True
    return Enrollment.objects.filter(student=user, course=course).exists()


def get_course_sections(course: Course):
    return course.sections.prefetch_related("lessons").all()


def get_enrollment_progress(enrollment: Enrollment) -> dict:
    course = enrollment.course
    completed_lessons = set(
        enrollment.progress_records.filter(completed=True).values_list("lesson_id", flat=True)
    )
    passed_attempts = list(
        QuizAttempt.objects.filter(
            enrollment=enrollment,
            status=QuizAttempt.STATUS_SUBMITTED,
            is_passed=True,
        )
        .values("quiz_id")
        .annotate(best_score=Max("score"), last_submitted_at=Max("submitted_at"))
    )
    passed_quiz_map = {item["quiz_id"]: item for item in passed_attempts}

    section_progress = []
    total_lessons = 0
    total_completed_lessons = 0
    for section in get_course_sections(course):
        lessons = list(section.lessons.all())
        lesson_items = []
        section_completed = 0
        for lesson in lessons:
            is_completed = lesson.id in completed_lessons
            section_completed += int(is_completed)
            lesson_items.append(
                {
                    "id": lesson.id,
                    "title": lesson.title,
                    "order": lesson.order,
                    "is_completed": is_completed,
                }
            )
        total_lessons += len(lessons)
        total_completed_lessons += section_completed
        percentage = round((section_completed / len(lessons) * 100), 2) if lessons else 0
        section_progress.append(
            {
                "id": section.id,
                "title": section.title,
                "description": section.description,
                "order": section.order,
                "lesson_count": len(lessons),
                "completed_lessons": section_completed,
                "progress_percentage": percentage,
                "lessons": lesson_items,
            }
        )

    published_quizzes = list(course.quizzes.filter(is_published=True).order_by("id"))
    quiz_progress = []
    for quiz in published_quizzes:
        quiz_pass = passed_quiz_map.get(quiz.id)
        quiz_progress.append(
            {
                "id": quiz.id,
                "title": quiz.title,
                "lesson_id": quiz.lesson_id,
                "passing_grade": quiz.passing_grade,
                "attempt_limit": quiz.attempt_limit,
                "best_score": round(quiz_pass["best_score"], 2) if quiz_pass else None,
                "is_passed": bool(quiz_pass),
            }
        )

    total_quizzes = len(published_quizzes)
    passed_quizzes = len(passed_quiz_map)
    total_units = total_lessons + total_quizzes
    completed_units = total_completed_lessons + passed_quizzes
    progress_percentage = round((completed_units / total_units * 100), 2) if total_units else 0
    is_completed = enrollment.is_course_completed()
    completed_at = enrollment.completed_at()

    return {
        "progress_percentage": progress_percentage,
        "total_lessons": total_lessons,
        "completed_lessons": total_completed_lessons,
        "total_quizzes": total_quizzes,
        "passed_quizzes": passed_quizzes,
        "is_completed": is_completed,
        "completed_at": to_isoformat(completed_at),
        "sections": section_progress,
        "quizzes": quiz_progress,
    }


def ensure_certificate_for_enrollment(enrollment: Enrollment) -> Certificate | None:
    if not enrollment.is_course_completed():
        return None

    completed_at = enrollment.completed_at()

    best_score = (
        QuizAttempt.objects.filter(
            enrollment=enrollment,
            status=QuizAttempt.STATUS_SUBMITTED,
        ).aggregate(value=Avg("score"))["value"]
        or 0
    )

    certificate, _ = Certificate.objects.get_or_create(
        course=enrollment.course,
        student=enrollment.student,
        defaults={
            "enrollment": enrollment,
            "code": secrets.token_hex(8).upper(),
            "final_score": round(best_score, 2),
            "metadata": {
                "completed_at": to_isoformat(completed_at),
            },
        },
    )
    return certificate


def render_certificate_pdf(certificate: Certificate) -> bytes:
    image = Image.new("RGB", (1400, 1000), "white")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.rectangle((40, 40, 1360, 960), outline="#1f2937", width=6)
    draw.text((500, 120), "CERTIFICATE", fill="#111827", font=title_font)
    draw.text((430, 230), "Simple LMS Extended", fill="#374151", font=body_font)
    draw.text((120, 360), "This certificate is awarded to:", fill="#6b7280", font=body_font)
    draw.text((120, 430), certificate.student.get_full_name() or certificate.student.username, fill="#111827", font=title_font)
    draw.text((120, 540), f"For successfully completing: {certificate.course.name}", fill="#111827", font=body_font)
    draw.text((120, 620), f"Issued at: {certificate.issued_at.astimezone(timezone.get_current_timezone()):%d %B %Y %H:%M}", fill="#374151", font=body_font)
    draw.text((120, 690), f"Verification code: {certificate.code}", fill="#374151", font=body_font)
    draw.text((120, 760), f"Final score: {certificate.final_score:.2f}", fill="#374151", font=body_font)

    buffer = BytesIO()
    image.save(buffer, format="PDF")
    return buffer.getvalue()


def build_student_recommendations(student, limit: int = 5):
    enrolled_course_ids = list(
        Enrollment.objects.filter(student=student).values_list("course_id", flat=True)
    )
    wishlisted_course_ids = list(
        CourseWishlist.objects.filter(student=student).values_list("course_id", flat=True)
    )
    preferred_category_ids = list(
        Course.objects.filter(id__in=enrolled_course_ids + wishlisted_course_ids)
        .exclude(category_id__isnull=True)
        .values_list("category_id", flat=True)
        .distinct()
    )

    queryset = annotate_courses(
        Course.objects.filter(status=Course.STATUS_PUBLISHED).exclude(id__in=enrolled_course_ids)
    )
    if preferred_category_ids:
        queryset = queryset.filter(category_id__in=preferred_category_ids)

    return list(queryset.order_by("-average_rating", "-student_count", "-created_at")[:limit])


def validate_quiz_payload(course: Course, lesson_id, questions: list[dict]):
    if lesson_id is not None and not course.lessons.filter(id=lesson_id).exists():
        raise HttpError(400, "Lesson does not belong to this course")

    if not questions:
        raise HttpError(400, "Quiz must contain at least one question")

    for index, question in enumerate(questions, start=1):
        options = question.get("options", [])
        if len(options) < 2:
            raise HttpError(400, f"Question {index} must contain at least two options")
        correct_count = sum(1 for option in options if option.get("is_correct"))
        if correct_count != 1:
            raise HttpError(400, f"Question {index} must contain exactly one correct option")


def replace_quiz_questions(quiz: Quiz, questions: list[dict]):
    quiz.questions.all().delete()
    for question_index, question_payload in enumerate(questions, start=1):
        question = QuizQuestion.objects.create(
            quiz=quiz,
            prompt=question_payload["prompt"],
            explanation=question_payload.get("explanation", ""),
            weight=question_payload.get("weight", 1),
            order=question_payload.get("order") or question_index,
        )
        for option_index, option_payload in enumerate(question_payload["options"], start=1):
            QuizOption.objects.create(
                question=question,
                text=option_payload["text"],
                is_correct=option_payload.get("is_correct", False),
                order=option_payload.get("order") or option_index,
            )


def start_quiz_attempt(quiz: Quiz, student):
    if not quiz.is_published:
        raise HttpError(400, "Quiz is not published yet")

    enrollment = Enrollment.objects.filter(student=student, course=quiz.course).first()
    if enrollment is None:
        raise HttpError(403, "You must enroll in this course before taking the quiz")

    existing_started_attempt = (
        QuizAttempt.objects.filter(
            quiz=quiz,
            student=student,
            status=QuizAttempt.STATUS_STARTED,
        )
        .order_by("-started_at")
        .first()
    )
    if existing_started_attempt is not None:
        return existing_started_attempt

    submitted_attempt_count = QuizAttempt.objects.filter(
        quiz=quiz,
        student=student,
        status=QuizAttempt.STATUS_SUBMITTED,
    ).count()
    if submitted_attempt_count >= quiz.attempt_limit:
        raise HttpError(400, "Attempt limit reached for this quiz")

    questions = list(quiz.questions.prefetch_related("options").all())
    if not questions:
        raise HttpError(400, "Quiz does not have any questions")

    if quiz.shuffle_questions:
        random.shuffle(questions)

    question_order = [question.id for question in questions]
    option_order: dict[str, list[int]] = {}
    for question in questions:
        option_ids = list(question.options.values_list("id", flat=True))
        if quiz.shuffle_options:
            random.shuffle(option_ids)
        option_order[str(question.id)] = option_ids

    return QuizAttempt.objects.create(
        quiz=quiz,
        student=student,
        enrollment=enrollment,
        question_order=question_order,
        option_order=option_order,
        total_points=quiz.total_points(),
    )


def build_attempt_session_payload(attempt: QuizAttempt) -> dict:
    quiz = attempt.quiz
    question_map = {
        question.id: question
        for question in quiz.questions.prefetch_related("options").all()
    }
    questions = []
    for question_id in attempt.question_order:
        question = question_map[question_id]
        ordered_option_ids = attempt.option_order.get(str(question_id), [])
        option_map = {option.id: option for option in question.options.all()}
        options = [
            {
                "id": option_id,
                "text": option_map[option_id].text,
                "order": index + 1,
            }
            for index, option_id in enumerate(ordered_option_ids)
            if option_id in option_map
        ]
        questions.append(
            {
                "id": question.id,
                "prompt": question.prompt,
                "explanation": question.explanation,
                "weight": question.weight,
                "order": question.order,
                "options": options,
            }
        )

    return {
        "attempt_id": attempt.id,
        "quiz_id": quiz.id,
        "quiz_title": quiz.title,
        "passing_grade": quiz.passing_grade,
        "attempt_limit": quiz.attempt_limit,
        "status": attempt.status,
        "started_at": to_isoformat(attempt.started_at),
        "questions": questions,
    }


def submit_quiz_attempt(attempt: QuizAttempt, answers: list[dict]):
    if attempt.status == QuizAttempt.STATUS_SUBMITTED:
        raise HttpError(400, "This attempt has already been submitted")

    questions = {
        question.id: question
        for question in attempt.quiz.questions.prefetch_related("options").all()
    }
    answers_by_question = {item["question_id"]: item.get("selected_option_id") for item in answers}
    total_points = 0
    earned_points = 0
    answer_details = []

    for question_id in attempt.question_order:
        question = questions[question_id]
        selected_option_id = answers_by_question.get(question_id)
        selected_option = None
        if selected_option_id is not None:
            selected_option = question.options.filter(id=selected_option_id).first()
            if selected_option is None:
                raise HttpError(400, f"Option {selected_option_id} is invalid for question {question_id}")

        correct_option = question.options.filter(is_correct=True).first()
        is_correct = correct_option is not None and selected_option is not None and correct_option.id == selected_option.id
        earned = question.weight if is_correct else 0

        StudentAnswer.objects.create(
            attempt=attempt,
            question=question,
            selected_option=selected_option,
            is_correct=is_correct,
            earned_points=earned,
        )

        total_points += question.weight
        earned_points += earned
        answer_details.append(
            {
                "question_id": question.id,
                "selected_option_id": selected_option.id if selected_option else None,
                "correct_option_id": correct_option.id if correct_option else None,
                "is_correct": is_correct,
                "earned_points": earned,
            }
        )

    score = round((earned_points / total_points * 100), 2) if total_points else 0
    attempt.status = QuizAttempt.STATUS_SUBMITTED
    attempt.submitted_at = timezone.now()
    attempt.total_points = total_points
    attempt.earned_points = earned_points
    attempt.score = score
    attempt.is_passed = score >= attempt.quiz.passing_grade
    attempt.save()

    certificate = ensure_certificate_for_enrollment(attempt.enrollment)
    return {
        "attempt_id": attempt.id,
        "quiz_id": attempt.quiz_id,
        "score": score,
        "earned_points": earned_points,
        "total_points": total_points,
        "is_passed": attempt.is_passed,
        "submitted_at": to_isoformat(attempt.submitted_at),
        "answers": answer_details,
        "certificate_code": certificate.code if certificate else None,
    }


def build_leaderboard(course: Course) -> list[dict]:
    leaderboard = []
    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("student", "course")
        .prefetch_related("progress_records", "quiz_attempts")
    )

    for enrollment in enrollments:
        quiz_stats = list(
            QuizAttempt.objects.filter(
                enrollment=enrollment,
                status=QuizAttempt.STATUS_SUBMITTED,
            )
            .values("quiz_id")
            .annotate(best_score=Max("score"))
        )
        best_quiz_score = round(
            sum(item["best_score"] for item in quiz_stats) / len(quiz_stats), 2
        ) if quiz_stats else 0

        progress_percentage = enrollment.progress_percentage()
        completed_at = enrollment.completed_at()
        completion_time_seconds = None
        if completed_at is not None:
            completion_time_seconds = max(
                (completed_at - enrollment.enrolled_at).total_seconds(),
                0,
            )

        leaderboard.append(
            {
                "student_id": enrollment.student_id,
                "student_name": enrollment.student.get_full_name() or enrollment.student.username,
                "best_quiz_score": best_quiz_score,
                "progress_percentage": progress_percentage,
                "completed_at": to_isoformat(completed_at),
                "completion_time_seconds": completion_time_seconds,
            }
        )

    leaderboard.sort(
        key=lambda item: (
            -item["best_quiz_score"],
            -item["progress_percentage"],
            item["completion_time_seconds"] if item["completion_time_seconds"] is not None else float("inf"),
            item["student_name"].lower(),
        )
    )

    for index, item in enumerate(leaderboard, start=1):
        item["rank"] = index
    return leaderboard


def build_review_summary(course: Course) -> dict:
    stats = course.reviews.aggregate(
        average_rating=Avg("rating"),
        review_count=Count("id"),
    )
    return {
        "average_rating": round(stats["average_rating"] or 0, 2),
        "review_count": stats["review_count"] or 0,
    }
