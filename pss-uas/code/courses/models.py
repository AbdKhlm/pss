from datetime import datetime
from typing import TYPE_CHECKING, cast

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.utils import timezone


# ======================
# USER
# ======================
class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('instructor', 'Instructor'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.username} ({self.role})"


# ======================
# CATEGORY
# ======================
class Category(models.Model):
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='subcategories',  # lebih jelas
        on_delete=models.CASCADE
    )

    def __str__(self):
        return self.name


# ======================
# COURSE QUERYSET
# ======================
class CourseQuerySet(models.QuerySet):
    def for_listing(self):
        return (
            self.select_related('instructor', 'category')
            .prefetch_related('sections', 'lessons')
            .annotate(
                lesson_count=models.Count('lessons', distinct=True),
                student_count=models.Count('enrollments', distinct=True),
                review_count=models.Count('reviews', distinct=True),
                average_rating=models.Avg('reviews__rating'),
            )
        )


# ======================
# COURSE
# ======================
class Course(models.Model):
    LEVEL_BEGINNER = "beginner"
    LEVEL_INTERMEDIATE = "intermediate"
    LEVEL_ADVANCED = "advanced"
    LEVEL_CHOICES = (
        (LEVEL_BEGINNER, "Beginner"),
        (LEVEL_INTERMEDIATE, "Intermediate"),
        (LEVEL_ADVANCED, "Advanced"),
    )

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    )

    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.IntegerField(default=0)
    image = models.CharField(max_length=255, blank=True, default="")
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_BEGINNER)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)

    instructor = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='instructed_courses'
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        related_name='courses'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    if TYPE_CHECKING:
        objects: CourseQuerySet
    else:
        objects = cast(CourseQuerySet, CourseQuerySet.as_manager())  # pyright: ignore[reportCallIssue]

    def __str__(self):
        return self.name

    @property
    def teacher(self):
        return self.instructor


class CourseSection(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='sections',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    order = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'order'],
                name='unique_section_order_per_course',
            )
        ]

    def __str__(self):
        return f"{self.course.name} - Section {self.order}: {self.title}"


# ======================
# LESSON
# ======================
class Lesson(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='lessons'
    )
    section = models.ForeignKey(
        CourseSection,
        on_delete=models.CASCADE,
        related_name='lessons',
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['section__order', 'order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'order'],
                name='unique_lesson_order_per_course'
            )
        ]

    def __str__(self):
        return f"{self.course.name} - {self.title}"


# ======================
# ENROLLMENT QUERYSET
# ======================
class EnrollmentQuerySet(models.QuerySet):
    def for_student_dashboard(self):
        return (
            self.select_related('course', 'course__instructor')
            .prefetch_related(
                'course__lessons',
                'progress_records'
            )
            .annotate(
                total_lessons=models.Count('course__lessons', distinct=True),
                completed_lessons=models.Count(
                    'progress_records',
                    filter=models.Q(progress_records__completed=True),
                    distinct=True
                )
            )
        )


# ======================
# ENROLLMENT
# ======================
class Enrollment(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='enrollments'
    )

    enrolled_at = models.DateTimeField(auto_now_add=True)

    if TYPE_CHECKING:
        objects: EnrollmentQuerySet
    else:
        objects = cast(EnrollmentQuerySet, EnrollmentQuerySet.as_manager())  # pyright: ignore[reportCallIssue]

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'course'],
                name='unique_enrollment'
            )
        ]
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['course']),
        ]

    def __str__(self):
        return f"{self.student} -> {self.course}"

    def progress_percentage(self) -> float:
        total_lessons = self.course.lessons.count()
        completed_lessons = self.progress_records.filter(completed=True).count()
        total_quizzes = self.course.quizzes.filter(is_published=True).count()
        passed_quizzes = (
            QuizAttempt.objects.filter(
                enrollment=self,
                status=QuizAttempt.STATUS_SUBMITTED,
                is_passed=True,
            )
            .values('quiz_id')
            .distinct()
            .count()
        )
        total_units = total_lessons + total_quizzes
        completed_units = completed_lessons + passed_quizzes
        return round((completed_units / total_units * 100), 2) if total_units else 0

    def completed_at(self) -> datetime | None:
        latest_lesson_completion = self.progress_records.filter(completed=True).aggregate(
            latest=models.Max('completed_at')
        )['latest']
        latest_quiz_completion = QuizAttempt.objects.filter(
            enrollment=self,
            status=QuizAttempt.STATUS_SUBMITTED,
            is_passed=True,
        ).aggregate(latest=models.Max('submitted_at'))['latest']
        timestamps = [value for value in [latest_lesson_completion, latest_quiz_completion] if value]
        return max(timestamps) if timestamps else None

    def is_course_completed(self) -> bool:
        total_lessons = self.course.lessons.count()
        completed_lessons = self.progress_records.filter(completed=True).count()
        total_quizzes = self.course.quizzes.filter(is_published=True).count()
        passed_quizzes = (
            QuizAttempt.objects.filter(
                enrollment=self,
                status=QuizAttempt.STATUS_SUBMITTED,
                is_passed=True,
            )
            .values('quiz_id')
            .distinct()
            .count()
        )

        lessons_done = total_lessons == 0 or completed_lessons == total_lessons
        quizzes_done = total_quizzes == 0 or passed_quizzes == total_quizzes
        return lessons_done and quizzes_done


# ======================
# PROGRESS
# ======================
class Progress(models.Model):
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='progress_records'
    )

    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'lesson'],
                name='unique_progress_per_lesson'
            )
        ]

    def save(self, *args, **kwargs):
        if self.completed and not self.completed_at:
            self.completed_at = timezone.now()
        super().save(*args, **kwargs)


class CourseReview(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='course_reviews',
        limit_choices_to=Q(role='student'),
    )
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'student'],
                name='unique_review_per_student_course',
            ),
            models.CheckConstraint(
                check=Q(rating__gte=1) & Q(rating__lte=5),
                name='review_rating_between_1_and_5',
            ),
        ]

    def __str__(self):
        return f"{self.student.username} rated {self.course.name} ({self.rating})"


class CourseWishlist(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='wishlists',
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='wishlist_items',
        limit_choices_to=Q(role='student'),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'student'],
                name='unique_wishlist_per_student_course',
            )
        ]

    def __str__(self):
        return f"{self.student.username} wishlist -> {self.course.name}"


class Quiz(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='quizzes',
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='quizzes',
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    instructions = models.TextField(blank=True, default="")
    passing_grade = models.PositiveIntegerField(default=70)
    attempt_limit = models.PositiveIntegerField(default=3)
    shuffle_questions = models.BooleanField(default=True)
    shuffle_options = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.title

    def total_points(self):
        return self.questions.aggregate(total=models.Sum('weight'))['total'] or 0


class QuizQuestion(models.Model):
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
    )
    prompt = models.TextField()
    explanation = models.TextField(blank=True, default="")
    weight = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['quiz', 'order'],
                name='unique_question_order_per_quiz',
            )
        ]

    def __str__(self):
        return f"{self.quiz.title} - Q{self.order}"


class QuizOption(models.Model):
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name='options',
    )
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['question', 'order'],
                name='unique_option_order_per_question',
            )
        ]

    def __str__(self):
        return f"{self.question} - Option {self.order}"


class QuizAttempt(models.Model):
    STATUS_STARTED = "started"
    STATUS_SUBMITTED = "submitted"
    STATUS_CHOICES = (
        (STATUS_STARTED, "Started"),
        (STATUS_SUBMITTED, "Submitted"),
    )

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
        limit_choices_to=Q(role='student'),
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='quiz_attempts',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_STARTED)
    question_order = models.JSONField(default=list, blank=True)
    option_order = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    total_points = models.PositiveIntegerField(default=0)
    earned_points = models.PositiveIntegerField(default=0)
    score = models.FloatField(default=0)
    is_passed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at', '-id']

    def __str__(self):
        return f"{self.student.username} - {self.quiz.title} ({self.status})"


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt,
        on_delete=models.CASCADE,
        related_name='answers',
    )
    question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.CASCADE,
        related_name='student_answers',
    )
    selected_option = models.ForeignKey(
        QuizOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_answers',
    )
    is_correct = models.BooleanField(default=False)
    earned_points = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['question__order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['attempt', 'question'],
                name='unique_answer_per_attempt_question',
            )
        ]


class Certificate(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='certificates',
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='certificates',
        limit_choices_to=Q(role='student'),
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.CASCADE,
        related_name='certificates',
    )
    code = models.CharField(max_length=32, unique=True)
    final_score = models.FloatField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'student'],
                name='unique_certificate_per_student_course',
            )
        ]

    def __str__(self):
        return f"{self.student.username} - {self.course.name} ({self.code})"
