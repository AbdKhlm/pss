from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Certificate,
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
    StudentAnswer,
    User,
)


# ======================
# LESSON INLINE
# ======================
class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    ordering = ('order',)


class CourseSectionInline(admin.TabularInline):
    model = CourseSection
    extra = 1
    ordering = ('order',)


# ======================
# USER
# ======================
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'is_superuser', 'is_active')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('username',)

    def get_fieldsets(self, request, obj=None):
        fieldsets = list(super().get_fieldsets(request, obj))
        fieldsets.append(('Simple LMS', {'fields': ('role',)}))
        return tuple(fieldsets)


# ======================
# CATEGORY
# ======================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'parent')
    search_fields = ('name',)


# ======================
# COURSE
# ======================
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'level', 'instructor', 'category', 'lesson_count', 'price')
    list_filter = ('status', 'level', 'category', 'instructor')
    search_fields = ('name', 'description')
    inlines = [CourseSectionInline, LessonInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related('instructor', 'category')
            .prefetch_related('sections', 'lessons')
        )

    def lesson_count(self, obj):
        return obj.lessons.count()


@admin.register(CourseSection)
class CourseSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    search_fields = ('title', 'course__name')


# ======================
# ENROLLMENT
# ======================
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'enrolled_at', 'progress_percent')
    search_fields = ('student__username', 'course__name')
    list_filter = ('course',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('student', 'course')

    def progress_percent(self, obj):
        return f"{obj.progress_percentage():.1f}%"


# ======================
# PROGRESS
# ======================
@admin.register(Progress)
class ProgressAdmin(admin.ModelAdmin):
    list_display = ('student', 'lesson', 'completed', 'completed_at')
    list_filter = ('completed',)
    search_fields = ('student__username', 'lesson__title')


@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'rating', 'updated_at')
    list_filter = ('rating', 'course')
    search_fields = ('course__name', 'student__username', 'comment')


@admin.register(CourseWishlist)
class CourseWishlistAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'created_at')
    list_filter = ('course',)
    search_fields = ('course__name', 'student__username')


class QuizOptionInline(admin.TabularInline):
    model = QuizOption
    extra = 1
    ordering = ('order',)


@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'order', 'weight', 'short_prompt')
    list_filter = ('quiz',)
    search_fields = ('prompt', 'quiz__title')
    inlines = [QuizOptionInline]

    def short_prompt(self, obj):
        return obj.prompt[:60]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'lesson', 'passing_grade', 'attempt_limit', 'is_published')
    list_filter = ('is_published', 'course')
    search_fields = ('title', 'course__name')


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ('quiz', 'student', 'status', 'score', 'is_passed', 'started_at', 'submitted_at')
    list_filter = ('status', 'is_passed', 'quiz')
    search_fields = ('quiz__title', 'student__username')


@admin.register(StudentAnswer)
class StudentAnswerAdmin(admin.ModelAdmin):
    list_display = ('attempt', 'question', 'selected_option', 'is_correct', 'earned_points')
    list_filter = ('is_correct',)
    search_fields = ('attempt__student__username', 'question__prompt')


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ('code', 'course', 'student', 'final_score', 'issued_at')
    list_filter = ('course',)
    search_fields = ('code', 'course__name', 'student__username')
