from django.contrib import admin
from .models import User, Category, Course, Lesson, Enrollment, Progress


# ======================
# LESSON INLINE
# ======================
class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 1
    ordering = ('order',)


# ======================
# USER
# ======================
@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'role', 'is_staff')
    list_filter = ('role', 'is_staff')
    search_fields = ('username', 'email')


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
    list_display = ('title', 'instructor', 'category', 'lesson_count')
    list_filter = ('category', 'instructor')
    search_fields = ('title',)
    inlines = [LessonInline]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('instructor', 'category')

    def lesson_count(self, obj):
        return obj.lessons.count()


# ======================
# ENROLLMENT
# ======================
@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'enrolled_at', 'progress_percent')
    search_fields = ('student__username', 'course__title')
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