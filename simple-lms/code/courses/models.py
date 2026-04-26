from django.db import models
from django.contrib.auth.models import AbstractUser
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
            .prefetch_related('lessons')
            .annotate(
                lesson_count=models.Count('lessons', distinct=True),
                student_count=models.Count('enrollments', distinct=True),
            )
        )


# ======================
# COURSE
# ======================
class Course(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()

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

    objects = CourseQuerySet.as_manager()

    def __str__(self):
        return self.title


# ======================
# LESSON
# ======================
class Lesson(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='lessons'
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(
                fields=['course', 'order'],
                name='unique_lesson_order_per_course'
            )
        ]

    def __str__(self):
        return f"{self.course.title} - {self.title}"


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

    objects = EnrollmentQuerySet.as_manager()

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

    # 🔥 BONUS (nilai plus)
    def progress_percentage(self):
        total = self.course.lessons.count()
        completed = self.progress_records.filter(completed=True).count()
        return (completed / total * 100) if total else 0


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