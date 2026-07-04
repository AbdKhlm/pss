from typing import List, Optional
from celery.result import AsyncResult
from ninja import NinjaAPI, Query
from ninja.errors import HttpError
from ninja_simple_jwt.auth.views.api import mobile_auth_router
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from courses.models import Course, Lesson, User, Category, Enrollment, Progress
from core.schemas import (
    CourseIn, CourseOut, DetailCourseOut, CourseUpdateIn,
    UserOut, UserRegisterIn, UserUpdateIn,
    MessageOut, EnrollmentOut, EnrollmentIn,
    ProgressIn, ActivityLogOut, LearningAnalyticsOut, MongoSyncOut,
    TaskDemoIn, TaskQueuedOut, TaskResultOut
)
from core.utils import is_admin, is_instructor, is_student
from core.mongo import (
    delete_activity_logs,
    get_learning_analytics,
    list_activity_logs,
    log_activity,
    sync_learning_analytics,
    update_activity_logs,
)
from core.tasks import add_numbers, send_enrollment_email, generate_certificate, export_course_report


# Inisialisasi API
api = NinjaAPI(title="Simple LMS API", version="1.0", description="REST API for Simple LMS")

# Register auth router dari ninja-simple-jwt
# Ini menyediakan endpoint /auth/sign-in dan /auth/token-refresh
api.add_router("/auth/", mobile_auth_router)

# Inisialisasi JWT auth handler
# Digunakan sebagai parameter auth= pada endpoint yang butuh authentication
apiAuth = HttpJwtAuth()


# Rate limiting decorator (using Redis)
def rate_limit(request, limit=60, period=60):
    key = f"rate_limit:{request.user.id if hasattr(request, 'user') and request.user.is_authenticated else request.META.get('REMOTE_ADDR')}"
    count = cache.get(key, 0)
    if count >= limit:
        raise HttpError(429, "Too many requests")
    cache.set(key, count + 1, timeout=period)
    return True


def clear_cache_pattern(pattern):
    """Clear all cache keys matching a pattern using scan_iter"""
    try:
        from django.core.cache import caches
        redis_cache = caches["default"]
        if not hasattr(redis_cache, "client"):
            return
        # Get the underlying Redis client
        client = redis_cache.client.get_client()
        for key in client.scan_iter(pattern):
            client.delete(key)
    except Exception as e:
        print(f"Error clearing cache: {e}")


def get_accessible_course_ids(user):
    if user.role == "admin":
        return None
    return list(Course.objects.filter(instructor=user).values_list("id", flat=True))


# ======================
# AUTH ENDPOINTS (Registration, Me, Update)
# ======================
@api.post('/auth/register', response=UserOut, tags=["Authentication"])
def register(request, data: UserRegisterIn):
    # Rate limiting
    rate_limit(request)

    # Cek apakah username sudah digunakan
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username already used")
    
    # Cek apakah email sudah digunakan
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email already used")
    
    # Buat user baru
    # create_user() otomatis melakukan hashing pada password
    new_user = User.objects.create_user(
        username=data.username,
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role
    )

    # Log activity
    log_activity(
        user_id=new_user.id,
        user_role=new_user.role,
        action="USER_REGISTER",
        metadata={"username": new_user.username},
        user=new_user,
    )

    return new_user


@api.get('/auth/me', response=UserOut, auth=apiAuth, tags=["Authentication"])
def get_current_user(request):
    rate_limit(request)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="USER_GET_ME",
        user=request.user,
    )
    return request.user


@api.put('/auth/me', response=UserOut, auth=apiAuth, tags=["Authentication"])
def update_profile(request, data: UserUpdateIn):
    rate_limit(request)
    user = request.user
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(user, attr, value)
    user.save()
    
    log_activity(
        user_id=user.id,
        user_role=user.role,
        action="USER_UPDATE_PROFILE",
        user=user,
    )
    return user


# ======================
# COURSES ENDPOINTS (Public with caching)
# ======================
@api.get('/courses', response=List[CourseOut], tags=["Courses"])
def list_courses(
    request,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    limit: int = 10,
    offset: int = 0
):
    rate_limit(request)
    cache_key = f"courses_list:{search or ''}:{category_id or ''}:{limit}:{offset}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    courses = Course.objects.select_related("instructor", "category")
    if search:
        courses = courses.filter(name__icontains=search)
    if category_id:
        courses = courses.filter(category_id=category_id)
    
    # Fix: Assign teacher = instructor for CourseOut
    result = []
    for course in courses[offset:offset+limit]:
        course.teacher = course.instructor
        result.append(course)
    cache.set(cache_key, result, 300)  # Cache for 5 minutes
    return result


@api.get('/courses/{course_id}', response=DetailCourseOut, tags=["Courses"])
def get_course(request, course_id: int):
    rate_limit(request)
    cache_key = f"course_detail:{course_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached
    
    course = get_object_or_404(Course, id=course_id)
    course.teacher = course.instructor
    course.contents = [
        {"id": lesson.id, "title": lesson.title}
        for lesson in course.lessons.all()
    ]
    cache.set(cache_key, course, 300)

    log_activity(
        user_id=request.user.id if hasattr(request, 'user') and request.user.is_authenticated else None,
        user_role=request.user.role if hasattr(request, 'user') and request.user.is_authenticated else None,
        action="COURSE_VIEW",
        course_id=course_id,
        user=request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
        course=course,
    )

    return course


# ======================
# COURSES ENDPOINTS (Protected)
# ======================
@api.post('/courses', response={201: CourseOut}, auth=apiAuth, tags=["Courses"])
@is_instructor
def create_course(request, data: CourseIn):
    rate_limit(request)
    category = None
    if data.category_id:
        category = get_object_or_404(Category, id=data.category_id)
    course = Course.objects.create(
        name=data.name,
        description=data.description,
        price=data.price,
        instructor=request.user,
        category=category,
    )
    course.teacher = course.instructor

    # Invalidate cache
    clear_cache_pattern("courses_list:*")

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_CREATE",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    return 201, course


@api.patch('/courses/{course_id}', response=CourseOut, auth=apiAuth, tags=["Courses"])
def update_course(request, course_id: int, data: CourseUpdateIn):
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    if request.user.role != "admin" and course.instructor != request.user:
        raise HttpError(403, "Forbidden")
    
    for attr, value in data.dict(exclude_unset=True).items():
        if attr == "category_id":
            course.category = get_object_or_404(Category, id=value) if value else None
        else:
            setattr(course, attr, value)
    course.save()
    course.teacher = course.instructor

    # Invalidate cache
    clear_cache_pattern("courses_list:*")
    cache.delete(f"course_detail:{course_id}")

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_UPDATE",
        course_id=course_id,
        user=request.user,
        course=course,
    )
    return course


@api.delete('/courses/{course_id}', response={204: None}, auth=apiAuth, tags=["Courses"])
@is_admin
def delete_course(request, course_id: int):
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    course.delete()

    # Invalidate cache
    clear_cache_pattern("courses_list:*")
    cache.delete(f"course_detail:{course_id}")

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_DELETE",
        course_id=course_id,
        user=request.user,
        course=course,
    )
    return 204, None


# ======================
# ENROLLMENTS ENDPOINTS
# ======================
@api.post('/enrollments', response={201: EnrollmentOut}, auth=apiAuth, tags=["Enrollments"])
@is_student
def enroll(request, data: EnrollmentIn):
    rate_limit(request)
    course = get_object_or_404(Course, id=data.course_id)
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        raise HttpError(400, "Already enrolled")
    enrollment = Enrollment.objects.create(
        student=request.user,
        course=course,
    )
    enrollment.course.teacher = enrollment.course.instructor

    # Send email via Celery
    send_enrollment_email.delay(request.user.email, course.name)

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="ENROLLMENT_CREATE",
        course_id=course.id,
        user=request.user,
        course=course,
    )

    return 201, enrollment


@api.get('/enrollments/my-courses', response=List[EnrollmentOut], auth=apiAuth, tags=["Enrollments"])
@is_student
def my_enrollments(request):
    rate_limit(request)
    enrollments = Enrollment.objects.filter(student=request.user).select_related("course", "course__instructor")
    for enrollment in enrollments:
        enrollment.course.teacher = enrollment.course.instructor
    return enrollments


@api.post('/enrollments/{enrollment_id}/progress', response=MessageOut, auth=apiAuth, tags=["Enrollments"])
@is_student
def mark_lesson_complete(request, enrollment_id: int, data: ProgressIn):
    rate_limit(request)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=request.user)
    lesson = get_object_or_404(Lesson, id=data.lesson_id, course=enrollment.course)
    progress, created = Progress.objects.get_or_create(
        student=request.user,
        lesson=lesson,
        enrollment=enrollment,
        defaults={"completed": True, "completed_at": timezone.now()}
    )
    if not created:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="LESSON_COMPLETE",
        course_id=enrollment.course.id,
        lesson_id=lesson.id,
        user=request.user,
        course=enrollment.course,
        lesson=lesson,
    )

    # Check if course is complete to generate certificate
    total_lessons = enrollment.course.lessons.count()
    completed_lessons = Progress.objects.filter(enrollment=enrollment, completed=True).count()
    if total_lessons == completed_lessons:
        generate_certificate.delay(request.user.id, enrollment.course.id)

    return {"message": "Lesson marked as complete"}


# ======================
# REPORT ENDPOINTS
# ======================
@api.post('/courses/{course_id}/export-report', response=MessageOut, auth=apiAuth, tags=["Courses"])
@is_instructor
def export_report(request, course_id: int):
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    if request.user.role != "admin" and course.instructor != request.user:
        raise HttpError(403, "Forbidden")
    export_course_report.delay(course_id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_EXPORT_REPORT",
        course_id=course_id,
        user=request.user,
        course=course,
    )
    return {"message": "Report export started, check Celery logs for details"}


# ======================
# ANALYTICS ENDPOINTS (MongoDB)
# ======================
@api.get('/analytics/activity-logs', response=List[ActivityLogOut], auth=apiAuth, tags=["Analytics"])
@is_instructor
def get_activity_logs(
    request,
    course_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    rate_limit(request)
    filters = {}

    if request.user.role != "admin":
        accessible_course_ids = get_accessible_course_ids(request.user)
        filters["course_id"] = {"$in": accessible_course_ids}
        if course_id and course_id not in accessible_course_ids:
            raise HttpError(403, "Forbidden")

    if course_id:
        filters["course_id"] = course_id
    if action:
        filters["action"] = action

    logs = list_activity_logs(filters=filters, limit=limit, skip=offset)
    for log in logs:
        log["id"] = log.pop("_id")
    return logs


@api.get('/analytics/learning', response=List[LearningAnalyticsOut], auth=apiAuth, tags=["Analytics"])
@is_instructor
def learning_analytics(request, course_id: Optional[int] = None, refresh: bool = False):
    rate_limit(request)
    if request.user.role != "admin" and course_id:
        course = get_object_or_404(Course, id=course_id)
        if course.instructor_id != request.user.id:
            raise HttpError(403, "Forbidden")

    analytics = get_learning_analytics(course_id=course_id, refresh=refresh)
    if request.user.role == "admin":
        return analytics

    accessible_course_ids = set(get_accessible_course_ids(request.user))
    return [item for item in analytics if item.get("course_id") in accessible_course_ids]


@api.post('/analytics/learning/rebuild', response=MongoSyncOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def rebuild_learning_analytics(request, course_id: Optional[int] = None):
    rate_limit(request)
    result = sync_learning_analytics(course_id=course_id)
    return {
        "message": "Learning analytics collection synced",
        "synced_count": result["synced_count"],
    }


@api.patch('/analytics/activity-logs/review', response=MongoSyncOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def review_activity_logs(request, action: str = "COURSE_VIEW"):
    rate_limit(request)
    result = update_activity_logs(
        filters={"action": action},
        updates={"reviewed": True},
    )
    return {
        "message": "Activity logs updated",
        "synced_count": result["modified_count"],
    }


@api.delete('/analytics/activity-logs', response=MessageOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def remove_activity_logs(request, action: str):
    rate_limit(request)
    deleted_count = delete_activity_logs(filters={"action": action})
    return {"message": f"Deleted {deleted_count} activity logs"}


# ======================
# TASK DEMO ENDPOINTS (Celery / RabbitMQ)
# ======================
@api.post('/tasks/demo-add', response=TaskQueuedOut, auth=apiAuth, tags=["Async Tasks"])
def queue_add_demo(request, data: TaskDemoIn):
    rate_limit(request)
    async_result = add_numbers.apply_async(args=[data.x, data.y], countdown=data.countdown)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="TASK_DEMO_ADD_ENQUEUED",
        metadata={"task_id": async_result.id, "x": data.x, "y": data.y, "countdown": data.countdown},
        user=request.user,
    )
    return {
        "message": "Task queued successfully",
        "task_id": async_result.id,
        "queue": "celery",
    }


@api.get('/tasks/{task_id}', response=TaskResultOut, auth=apiAuth, tags=["Async Tasks"])
def get_task_status(request, task_id: str):
    rate_limit(request)
    task_result = AsyncResult(task_id)
    payload = task_result.result
    if isinstance(payload, Exception):
        payload = str(payload)

    return {
        "task_id": task_id,
        "status": task_result.status,
        "ready": task_result.ready(),
        "successful": task_result.successful() if task_result.ready() else False,
        "result": payload,
    }
