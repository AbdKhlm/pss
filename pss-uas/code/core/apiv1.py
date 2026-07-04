from datetime import datetime
from typing import List, Optional

from celery.result import AsyncResult
from django.contrib.auth import authenticate
from django.contrib.auth.signals import user_logged_in
from django.core.cache import cache
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, HttpError
from ninja_simple_jwt.auth.views.api import mobile_auth_router
from ninja_simple_jwt.jwt.token_operations import (
    get_access_token_for_user,
    get_refresh_token_for_user,
)

from core.auth import SwaggerFriendlyJwtAuth
from core.mongo import (
    delete_activity_logs,
    get_learning_analytics,
    list_activity_logs,
    log_activity,
    sync_learning_analytics,
    update_activity_logs,
)
from core.schemas import (
    ActivityLogOut,
    CertificateOut,
    CertificateVerificationOut,
    CourseIn,
    CourseOut,
    CourseSectionIn,
    CourseSectionUpdateIn,
    CourseUpdateIn,
    DashboardOut,
    DetailCourseOut,
    EnrollmentIn,
    EnrollmentOut,
    EnrollmentProgressOut,
    LeaderboardEntryOut,
    LearningAnalyticsOut,
    LessonIn,
    LessonOut,
    LessonUpdateIn,
    LoginIn,
    MessageOut,
    MongoSyncOut,
    ProgressIn,
    QuizAttemptHistoryOut,
    QuizAttemptResultOut,
    QuizAttemptStartOut,
    QuizDetailOut,
    QuizIn,
    QuizSubmitIn,
    QuizSummaryOut,
    QuizUpdateIn,
    ReviewIn,
    ReviewOut,
    TaskDemoIn,
    TaskQueuedOut,
    TaskResultOut,
    TokenPairOut,
    UserOut,
    UserRegisterIn,
    UserUpdateIn,
    WishlistOut,
)
from core.tasks import add_numbers, export_course_report, generate_certificate, send_enrollment_email
from core.utils import get_user_role, is_admin, is_instructor, is_student
from courses.models import (
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
    User,
)
from courses.services import (
    annotate_courses,
    build_attempt_session_payload,
    build_leaderboard,
    build_student_recommendations,
    can_manage_course,
    can_view_course,
    ensure_certificate_for_enrollment,
    get_enrollment_progress,
    render_certificate_pdf,
    replace_quiz_questions,
    start_quiz_attempt,
    submit_quiz_attempt,
    validate_quiz_payload,
)


api = NinjaAPI(
    title="Simple LMS Extended API",
    version="2.0",
    description=(
        "Backend untuk Simple LMS Extended dengan JWT authentication, course discovery, "
        "curriculum & progress detail, wishlist, review, quiz, certificate, leaderboard, "
        "analytics MongoDB, dan async task Celery."
    ),
)
apiAuth = SwaggerFriendlyJwtAuth()


def to_isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def resolve_optional_user(request: HttpRequest):
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        return getattr(request, "user", None)

    try:
        apiAuth.authenticate(request, authorization)
    except AuthenticationError as exc:
        status_code = getattr(exc, "status_code", 401) or 401
        message = getattr(exc, "message", "Invalid or expired token")
        raise HttpError(status_code, message) from exc
    return request.user


def rate_limit(request, limit=60, period=60):
    key = (
        f"rate_limit:{request.user.id}"
        if hasattr(request, "user") and request.user.is_authenticated
        else f"rate_limit:{request.META.get('REMOTE_ADDR')}"
    )
    count = cache.get(key, 0)
    if count >= limit:
        raise HttpError(429, "Too many requests")
    cache.set(key, count + 1, timeout=period)
    return True


def clear_cache_pattern(pattern):
    try:
        from django.core.cache import caches

        redis_cache = caches["default"]
        if not hasattr(redis_cache, "client"):
            return
        client = redis_cache.client.get_client()
        for key in client.scan_iter(pattern):
            client.delete(key)
    except Exception:
        return


def get_accessible_course_ids(user):
    if get_user_role(user) == "admin":
        return None
    return list(Course.objects.filter(instructor=user).values_list("id", flat=True))


def invalidate_course_related_cache(course_id: Optional[int] = None):
    clear_cache_pattern("courses_list:*")
    clear_cache_pattern("dashboard:student:*")
    if course_id is not None:
        cache.delete(f"course_detail:{course_id}")


def serialize_course(course: Course):
    summary = {
        "average_rating": round(float(getattr(course, "average_rating", 0) or 0), 2),
        "review_count": int(getattr(course, "review_count", course.reviews.count() if hasattr(course, "reviews") else 0) or 0),
        "student_count": int(getattr(course, "student_count", course.enrollments.count() if hasattr(course, "enrollments") else 0) or 0),
        "wishlist_count": int(getattr(course, "wishlist_count", course.wishlists.count() if hasattr(course, "wishlists") else 0) or 0),
    }
    return {
        "id": course.id,
        "name": course.name,
        "description": course.description,
        "price": course.price,
        "image": course.image,
        "level": course.level,
        "status": course.status,
        "teacher": {
            "id": course.instructor.id,
            "username": course.instructor.username,
            "first_name": course.instructor.first_name,
            "last_name": course.instructor.last_name,
            "email": course.instructor.email,
        },
        "category": (
            {
                "id": course.category.id,
                "name": course.category.name,
                "parent_id": course.category.parent_id,
            }
            if course.category
            else None
        ),
        "created_at": course.created_at,
        "updated_at": course.updated_at,
        **summary,
    }


def serialize_course_detail(course: Course):
    sections = []
    contents = []
    for section in course.sections.prefetch_related("lessons").all():
        lesson_items = []
        for lesson in section.lessons.all():
            lesson_items.append(
                {
                    "id": lesson.id,
                    "title": lesson.title,
                    "order": lesson.order,
                    "is_completed": False,
                }
            )
            contents.append({"id": lesson.id, "title": lesson.title})
        sections.append(
            {
                "id": section.id,
                "title": section.title,
                "description": section.description,
                "order": section.order,
                "lessons": lesson_items,
            }
        )

    detail = serialize_course(course)
    detail["contents"] = contents
    detail["curriculum"] = sections
    detail["published_quiz_count"] = course.quizzes.filter(is_published=True).count()
    return detail


def serialize_enrollment(enrollment: Enrollment):
    completed_at = enrollment.completed_at()
    return {
        "id": enrollment.id,
        "course": serialize_course(enrollment.course),
        "enrolled_at": enrollment.enrolled_at,
        "progress_percentage": float(enrollment.progress_percentage()),
        "is_completed": bool(enrollment.is_course_completed()),
        "completed_at": to_isoformat(completed_at),
    }


def serialize_certificate(request, certificate: Certificate):
    return {
        "code": certificate.code,
        "issued_at": certificate.issued_at,
        "final_score": round(certificate.final_score, 2),
        "course": serialize_course(certificate.course),
        "verification_url": request.build_absolute_uri(f"/api/certificates/verify/{certificate.code}"),
    }


def require_course_management(request, course: Course):
    if not can_manage_course(request.user, course):
        raise HttpError(403, "Forbidden")


def require_course_visibility(request, course: Course):
    if not can_view_course(getattr(request, "user", None), course):
        raise HttpError(403, "Forbidden")


def validate_course_choices(level: Optional[str] = None, status: Optional[str] = None):
    if level and level not in dict(Course.LEVEL_CHOICES):
        raise HttpError(400, "Invalid level")
    if status and status not in dict(Course.STATUS_CHOICES):
        raise HttpError(400, "Invalid status")


@api.post("/auth/register", response=UserOut, tags=["Authentication"])
def register(request, data: UserRegisterIn):
    """Registrasi akun publik. Semua akun yang dibuat lewat endpoint ini akan menjadi student."""
    rate_limit(request)

    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username already used")
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email already used")

    new_user = User.objects.create_user(
        username=data.username,
        email=data.email,
        password=data.password,
        first_name=data.first_name,
        last_name=data.last_name,
        role="student",
    )

    log_activity(
        user_id=new_user.id,
        user_role=new_user.role,
        action="USER_REGISTER",
        metadata={"username": new_user.username},
        user=new_user,
    )
    return new_user


@api.post("/auth/login", response=TokenPairOut, tags=["Authentication"])
def login(request, data: LoginIn):
    """Login manual untuk Swagger dan API client."""
    rate_limit(request)
    user = authenticate(request, username=data.username, password=data.password)
    if user is None:
        raise HttpError(401, "Invalid username or password")

    user_logged_in.send(sender=user.__class__, request=request, user=user)
    refresh_token, _ = get_refresh_token_for_user(user)
    access_token, _ = get_access_token_for_user(user)

    log_activity(
        user_id=user.id,
        user_role=user.role,
        action="USER_LOGIN",
        metadata={"username": user.username},
        user=user,
    )
    return {"access": access_token, "refresh": refresh_token}


@api.get("/auth/me", response=UserOut, auth=apiAuth, tags=["Authentication"])
def get_current_user(request):
    """Ambil profil user yang sedang login."""
    rate_limit(request)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="USER_GET_ME",
        user=request.user,
    )
    return request.user


@api.put("/auth/me", response=UserOut, auth=apiAuth, tags=["Authentication"])
def update_profile(request, data: UserUpdateIn):
    """Update profil dasar user tanpa mengubah role."""
    rate_limit(request)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(request.user, attr, value)
    request.user.save()

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="USER_UPDATE_PROFILE",
        user=request.user,
    )
    return request.user


api.add_router("/auth/", mobile_auth_router)


@api.get("/courses", response=List[CourseOut], tags=["Courses"])
def list_courses(
    request,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    instructor_id: Optional[int] = None,
    level: Optional[str] = None,
    status: Optional[str] = None,
    sort: str = "newest",
    limit: int = 10,
    offset: int = 0,
):
    """
    List course dengan keyword search, filter category/instructor/level/status,
    dan sorting `newest`, `oldest`, `popular`, `rating`, `price_low`, `price_high`.
    """
    rate_limit(request)
    validate_course_choices(level=level, status=status)
    user = resolve_optional_user(request)
    is_authenticated = bool(user and user.is_authenticated)
    role = get_user_role(user) if is_authenticated else ""

    cacheable = not is_authenticated or role == "student"
    cache_key = (
        f"courses_list:{search or ''}:{category_id or ''}:{instructor_id or ''}:"
        f"{level or ''}:{status or ''}:{sort}:{limit}:{offset}:{role or 'anon'}"
    )
    if cacheable:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    courses = annotate_courses(Course.objects.all())
    if is_authenticated and role == "instructor":
        courses = courses.filter(Q(status=Course.STATUS_PUBLISHED) | Q(instructor=user))
    elif is_authenticated and role == "admin":
        pass
    else:
        courses = courses.filter(status=Course.STATUS_PUBLISHED)

    if search:
        courses = courses.filter(Q(name__icontains=search) | Q(description__icontains=search))
    if category_id:
        courses = courses.filter(category_id=category_id)
    if instructor_id:
        courses = courses.filter(instructor_id=instructor_id)
    if level:
        courses = courses.filter(level=level)
    if status:
        courses = courses.filter(status=status)

    sort_mapping = {
        "newest": "-created_at",
        "oldest": "created_at",
        "popular": "-student_count",
        "rating": "-average_rating",
        "price_low": "price",
        "price_high": "-price",
    }
    if sort not in sort_mapping:
        raise HttpError(400, "Invalid sort parameter")

    result = [serialize_course(course) for course in courses.order_by(sort_mapping[sort], "-id")[offset : offset + limit]]
    if cacheable:
        cache.set(cache_key, result, 300)
    return result


@api.get("/courses/{course_id}", response=DetailCourseOut, tags=["Courses"])
def get_course(request, course_id: int):
    """Ambil detail course termasuk curriculum section/module, lesson list, dan ringkasan rating."""
    rate_limit(request)
    cache_key = f"course_detail:{course_id}"
    user = resolve_optional_user(request)
    is_public_request = not bool(user and user.is_authenticated)
    if is_public_request:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    course = get_object_or_404(
        annotate_courses(Course.objects.all()).prefetch_related("sections__lessons", "quizzes"),
        id=course_id,
    )
    require_course_visibility(request, course)
    payload = serialize_course_detail(course)
    if is_public_request:
        cache.set(cache_key, payload, 300)

    log_activity(
        user_id=user.id if user and user.is_authenticated else None,
        user_role=user.role if user and user.is_authenticated else None,
        action="COURSE_VIEW",
        course_id=course.id,
        user=user if user and user.is_authenticated else None,
        course=course,
    )
    return payload


@api.post("/courses", response={201: CourseOut}, auth=apiAuth, tags=["Courses"])
@is_instructor
def create_course(request, data: CourseIn):
    """Buat course baru dengan metadata discovery seperti level dan status."""
    rate_limit(request)
    validate_course_choices(level=data.level, status=data.status)
    category = get_object_or_404(Category, id=data.category_id) if data.category_id else None
    course = Course.objects.create(
        name=data.name,
        description=data.description,
        price=data.price,
        image=data.image,
        level=data.level,
        status=data.status,
        instructor=request.user,
        category=category,
    )
    invalidate_course_related_cache(course.id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_CREATE",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    return 201, serialize_course(course)


@api.patch("/courses/{course_id}", response=CourseOut, auth=apiAuth, tags=["Courses"])
def update_course(request, course_id: int, data: CourseUpdateIn):
    """Update data course. Hanya admin atau instructor pemilik course yang boleh mengubah."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_management(request, course)
    validate_course_choices(level=data.level, status=data.status)

    for attr, value in data.dict(exclude_unset=True).items():
        if attr == "category_id":
            course.category = get_object_or_404(Category, id=value) if value else None
        else:
            setattr(course, attr, value)
    course.save()
    invalidate_course_related_cache(course.id)

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_UPDATE",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    return serialize_course(course)


@api.delete("/courses/{course_id}", response={204: None}, auth=apiAuth, tags=["Courses"])
@is_admin
def delete_course(request, course_id: int):
    """Hapus course. Endpoint ini dibatasi untuk admin."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_DELETE",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    course.delete()
    invalidate_course_related_cache(course_id)
    return 204, None


@api.post("/courses/{course_id}/sections", response=MessageOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def create_section(request, course_id: int, data: CourseSectionIn):
    """Tambah section/module pada course untuk struktur curriculum yang lebih detail."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_management(request, course)
    CourseSection.objects.create(
        course=course,
        title=data.title,
        description=data.description,
        order=data.order,
    )
    invalidate_course_related_cache(course.id)
    return {"message": "Section created"}


@api.patch("/sections/{section_id}", response=MessageOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def update_section(request, section_id: int, data: CourseSectionUpdateIn):
    """Update title, description, atau order sebuah section."""
    rate_limit(request)
    section = get_object_or_404(CourseSection.objects.select_related("course"), id=section_id)
    require_course_management(request, section.course)
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(section, attr, value)
    section.save()
    invalidate_course_related_cache(section.course_id)
    return {"message": "Section updated"}


@api.delete("/sections/{section_id}", response=MessageOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def delete_section(request, section_id: int):
    """Hapus section dari course."""
    rate_limit(request)
    section = get_object_or_404(CourseSection.objects.select_related("course"), id=section_id)
    require_course_management(request, section.course)
    course_id = section.course_id
    section.delete()
    invalidate_course_related_cache(course_id)
    return {"message": "Section deleted"}


@api.post("/courses/{course_id}/lessons", response=LessonOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def create_lesson(request, course_id: int, data: LessonIn):
    """Tambah lesson ke section tertentu di dalam course."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_management(request, course)
    section = get_object_or_404(CourseSection, id=data.section_id, course=course)
    lesson = Lesson.objects.create(
        course=course,
        section=section,
        title=data.title,
        content=data.content,
        order=data.order,
    )
    invalidate_course_related_cache(course.id)
    return {
        "id": lesson.id,
        "section_id": lesson.section_id,
        "title": lesson.title,
        "content": lesson.content,
        "order": lesson.order,
    }


@api.get("/lessons/{lesson_id}", response=LessonOut, auth=apiAuth, tags=["Curriculum"])
def get_lesson(request, lesson_id: int):
    """Ambil detail lesson. Student hanya boleh membuka lesson pada course yang sudah dia enroll."""
    rate_limit(request)
    lesson = get_object_or_404(
        Lesson.objects.select_related("course", "section", "course__instructor"),
        id=lesson_id,
    )
    course = lesson.course
    if not can_manage_course(request.user, course):
        is_enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
        if not is_enrolled:
            raise HttpError(403, "Forbidden")

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="LESSON_VIEW",
        course_id=course.id,
        lesson_id=lesson.id,
        user=request.user,
        course=course,
        lesson=lesson,
    )
    return {
        "id": lesson.id,
        "section_id": lesson.section_id,
        "title": lesson.title,
        "content": lesson.content,
        "order": lesson.order,
    }


@api.patch("/lessons/{lesson_id}", response=MessageOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def update_lesson(request, lesson_id: int, data: LessonUpdateIn):
    """Update lesson dan pindahkan section bila diperlukan."""
    rate_limit(request)
    lesson = get_object_or_404(Lesson.objects.select_related("course"), id=lesson_id)
    require_course_management(request, lesson.course)
    payload = data.dict(exclude_unset=True)
    if "section_id" in payload:
        lesson.section = get_object_or_404(CourseSection, id=payload.pop("section_id"), course=lesson.course)
    for attr, value in payload.items():
        setattr(lesson, attr, value)
    lesson.save()
    invalidate_course_related_cache(lesson.course_id)
    return {"message": "Lesson updated"}


@api.delete("/lessons/{lesson_id}", response=MessageOut, auth=apiAuth, tags=["Curriculum"])
@is_instructor
def delete_lesson(request, lesson_id: int):
    """Hapus lesson dari curriculum course."""
    rate_limit(request)
    lesson = get_object_or_404(Lesson.objects.select_related("course"), id=lesson_id)
    require_course_management(request, lesson.course)
    course_id = lesson.course_id
    lesson.delete()
    invalidate_course_related_cache(course_id)
    return {"message": "Lesson deleted"}


@api.get("/courses/{course_id}/reviews", response=List[ReviewOut], tags=["Reviews"])
def list_reviews(request, course_id: int):
    """Lihat ulasan course beserta identitas student yang memberi review."""
    rate_limit(request)
    resolve_optional_user(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_visibility(request, course)
    return course.reviews.select_related("student").all()


@api.post("/courses/{course_id}/reviews", response=ReviewOut, auth=apiAuth, tags=["Reviews"])
@is_student
def create_or_update_review(request, course_id: int, data: ReviewIn):
    """Student yang sudah enroll dapat memberi rating dan review atau memperbaruinya."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    if not Enrollment.objects.filter(student=request.user, course=course).exists():
        raise HttpError(403, "You must enroll in the course before leaving a review")
    if data.rating < 1 or data.rating > 5:
        raise HttpError(400, "Rating must be between 1 and 5")

    review, created = CourseReview.objects.update_or_create(
        course=course,
        student=request.user,
        defaults={"rating": data.rating, "comment": data.comment},
    )
    invalidate_course_related_cache(course.id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_REVIEW_CREATED" if created else "COURSE_REVIEW_UPDATED",
        course_id=course.id,
        metadata={"rating": data.rating},
        user=request.user,
        course=course,
    )
    return review


@api.delete("/courses/{course_id}/reviews/me", response=MessageOut, auth=apiAuth, tags=["Reviews"])
@is_student
def delete_my_review(request, course_id: int):
    """Hapus review milik student pada course tertentu."""
    rate_limit(request)
    review = get_object_or_404(CourseReview, course_id=course_id, student=request.user)
    review.delete()
    invalidate_course_related_cache(course_id)
    return {"message": "Review deleted"}


@api.post("/wishlist", response=MessageOut, auth=apiAuth, tags=["Wishlist"])
@is_student
def add_to_wishlist(request, data: EnrollmentIn):
    """Simpan course ke wishlist student."""
    rate_limit(request)
    course = get_object_or_404(Course, id=data.course_id, status=Course.STATUS_PUBLISHED)
    CourseWishlist.objects.get_or_create(course=course, student=request.user)
    invalidate_course_related_cache(course.id)
    return {"message": "Course added to wishlist"}


@api.get("/wishlist/my-courses", response=List[WishlistOut], auth=apiAuth, tags=["Wishlist"])
@is_student
def my_wishlist(request):
    """Lihat daftar course favorit student."""
    rate_limit(request)
    wishlist = CourseWishlist.objects.filter(student=request.user).select_related(
        "course",
        "course__instructor",
        "course__category",
    )
    return [
        {
            "id": item.id,
            "created_at": item.created_at,
            "course": serialize_course(item.course),
        }
        for item in wishlist
    ]


@api.delete("/wishlist/{course_id}", response=MessageOut, auth=apiAuth, tags=["Wishlist"])
@is_student
def remove_from_wishlist(request, course_id: int):
    """Hapus course dari wishlist student."""
    rate_limit(request)
    deleted_count, _ = CourseWishlist.objects.filter(course_id=course_id, student=request.user).delete()
    if not deleted_count:
        raise HttpError(404, "Wishlist item not found")
    invalidate_course_related_cache(course_id)
    return {"message": "Course removed from wishlist"}


@api.post("/enrollments", response={200: EnrollmentOut, 201: EnrollmentOut}, auth=apiAuth, tags=["Enrollments"])
@is_student
def enroll(request, data: EnrollmentIn):
    """Enroll student ke course published. Jika sudah pernah enroll, endpoint akan mengembalikan enrollment lama."""
    rate_limit(request)
    course = get_object_or_404(Course, id=data.course_id)
    if course.status != Course.STATUS_PUBLISHED and not can_manage_course(request.user, course):
        raise HttpError(400, "Course is not available for enrollment")

    existing_enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
    if existing_enrollment:
        return 200, serialize_enrollment(existing_enrollment)

    enrollment = Enrollment.objects.create(student=request.user, course=course)
    send_enrollment_email.delay(request.user.email, course.name)
    invalidate_course_related_cache(course.id)

    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="ENROLLMENT_CREATE",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    return 201, serialize_enrollment(enrollment)


@api.get("/enrollments/my-courses", response=List[EnrollmentOut], auth=apiAuth, tags=["Enrollments"])
@is_student
def my_enrollments(request):
    """Ambil daftar course yang sudah di-enroll student lengkap dengan progres total."""
    rate_limit(request)
    enrollments = (
        Enrollment.objects.filter(student=request.user)
        .select_related("course", "course__instructor", "course__category")
        .order_by("-enrolled_at")
    )
    return [serialize_enrollment(item) for item in enrollments]


@api.get("/enrollments/{enrollment_id}/progress", response=EnrollmentProgressOut, auth=apiAuth, tags=["Enrollments"])
@is_student
def get_enrollment_detail_progress(request, enrollment_id: int):
    """Progres detail per section, lesson, dan quiz untuk enrollment tertentu."""
    rate_limit(request)
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("course", "student"),
        id=enrollment_id,
        student=request.user,
    )
    return get_enrollment_progress(enrollment)


@api.post("/enrollments/{enrollment_id}/progress", response=MessageOut, auth=apiAuth, tags=["Enrollments"])
@is_student
def mark_lesson_complete(request, enrollment_id: int, data: ProgressIn):
    """Tandai lesson sebagai selesai dan evaluasi apakah course sudah memenuhi syarat completion."""
    rate_limit(request)
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=request.user)
    lesson = get_object_or_404(Lesson, id=data.lesson_id, course=enrollment.course)
    progress, created = Progress.objects.get_or_create(
        student=request.user,
        lesson=lesson,
        enrollment=enrollment,
        defaults={"completed": True, "completed_at": timezone.now()},
    )
    if not created:
        progress.completed = True
        progress.completed_at = timezone.now()
        progress.save()

    certificate = ensure_certificate_for_enrollment(enrollment)
    if certificate is not None:
        generate_certificate.delay(request.user.id, enrollment.course.id)

    invalidate_course_related_cache(enrollment.course_id)
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
    return {"message": "Lesson marked as complete"}


@api.get("/dashboard/student", response=DashboardOut, auth=apiAuth, tags=["Dashboard"])
@is_student
def student_dashboard(request):
    """Dashboard student berisi course aktif, course selesai, wishlist, dan rekomendasi sederhana."""
    rate_limit(request)
    cache_key = f"dashboard:student:{request.user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    enrollments = list(
        Enrollment.objects.filter(student=request.user)
        .select_related("course", "course__instructor", "course__category")
        .order_by("-enrolled_at")
    )
    active_courses = [serialize_enrollment(item) for item in enrollments if not item.is_course_completed()]
    completed_courses = [serialize_enrollment(item) for item in enrollments if item.is_course_completed()]
    wishlist_courses = [
        serialize_course(item.course)
        for item in CourseWishlist.objects.filter(student=request.user).select_related(
            "course",
            "course__instructor",
            "course__category",
        )
    ]
    recommendations = [serialize_course(course) for course in build_student_recommendations(request.user)]

    payload = {
        "active_courses": active_courses,
        "completed_courses": completed_courses,
        "wishlist_courses": wishlist_courses,
        "recommendations": recommendations,
    }
    cache.set(cache_key, payload, 300)
    return payload


@api.post("/courses/{course_id}/quizzes", response={201: QuizDetailOut}, auth=apiAuth, tags=["Assessments"])
@is_instructor
def create_quiz(request, course_id: int, data: QuizIn):
    """Buat quiz dan question bank lengkap untuk sebuah course atau lesson tertentu."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_management(request, course)
    validate_quiz_payload(course, data.lesson_id, [question.dict() for question in data.questions])

    quiz = Quiz.objects.create(
        course=course,
        lesson_id=data.lesson_id,
        title=data.title,
        description=data.description,
        instructions=data.instructions,
        passing_grade=data.passing_grade,
        attempt_limit=data.attempt_limit,
        shuffle_questions=data.shuffle_questions,
        shuffle_options=data.shuffle_options,
        is_published=data.is_published,
    )
    replace_quiz_questions(quiz, [question.dict() for question in data.questions])
    invalidate_course_related_cache(course.id)
    return 201, quiz


@api.get("/courses/{course_id}/quizzes", response=List[QuizSummaryOut], auth=apiAuth, tags=["Assessments"])
def list_course_quizzes(request, course_id: int):
    """List quiz pada course. Student harus sudah enroll, instructor/admin bisa melihat seluruh quiz milik course."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    is_manager = can_manage_course(request.user, course)
    is_enrolled = Enrollment.objects.filter(student=request.user, course=course).exists()
    if not is_manager and not is_enrolled:
        raise HttpError(403, "Forbidden")

    quizzes = course.quizzes.all()
    if not is_manager:
        quizzes = quizzes.filter(is_published=True)
    return list(quizzes)


@api.get("/quizzes/{quiz_id}", response=QuizDetailOut, auth=apiAuth, tags=["Assessments"])
def get_quiz(request, quiz_id: int):
    """Lihat detail quiz beserta question bank. Endpoint ini dibatasi untuk admin atau instructor pemilik course."""
    rate_limit(request)
    quiz = get_object_or_404(
        Quiz.objects.select_related("course", "lesson", "course__instructor").prefetch_related("questions__options"),
        id=quiz_id,
    )
    require_course_management(request, quiz.course)
    return quiz


@api.patch("/quizzes/{quiz_id}", response=QuizDetailOut, auth=apiAuth, tags=["Assessments"])
@is_instructor
def update_quiz(request, quiz_id: int, data: QuizUpdateIn):
    """Update metadata quiz dan optionally ganti seluruh bank soal dalam satu request."""
    rate_limit(request)
    quiz = get_object_or_404(Quiz.objects.select_related("course"), id=quiz_id)
    require_course_management(request, quiz.course)

    payload = data.dict(exclude_unset=True)
    if "questions" in payload:
        questions = payload.pop("questions")
        validate_quiz_payload(quiz.course, payload.get("lesson_id", quiz.lesson_id), questions)
        replace_quiz_questions(quiz, questions)
    if "lesson_id" in payload and payload["lesson_id"] is not None:
        if not quiz.course.lessons.filter(id=payload["lesson_id"]).exists():
            raise HttpError(400, "Lesson does not belong to this course")
    for attr, value in payload.items():
        setattr(quiz, attr, value)
    quiz.save()

    invalidate_course_related_cache(quiz.course_id)
    return quiz


@api.delete("/quizzes/{quiz_id}", response=MessageOut, auth=apiAuth, tags=["Assessments"])
@is_instructor
def delete_quiz(request, quiz_id: int):
    """Hapus quiz dari course."""
    rate_limit(request)
    quiz = get_object_or_404(Quiz.objects.select_related("course"), id=quiz_id)
    require_course_management(request, quiz.course)
    course_id = quiz.course_id
    quiz.delete()
    invalidate_course_related_cache(course_id)
    return {"message": "Quiz deleted"}


@api.post("/quizzes/{quiz_id}/attempts/start", response=QuizAttemptStartOut, auth=apiAuth, tags=["Assessments"])
@is_student
def begin_quiz_attempt(request, quiz_id: int):
    """Mulai atau lanjutkan attempt quiz dengan randomisasi urutan soal dan opsi jawaban."""
    rate_limit(request)
    quiz = get_object_or_404(Quiz.objects.prefetch_related("questions__options"), id=quiz_id)
    attempt = start_quiz_attempt(quiz, request.user)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="QUIZ_ATTEMPT_STARTED",
        course_id=quiz.course_id,
        metadata={"quiz_id": quiz.id, "attempt_id": attempt.id},
        user=request.user,
        course=quiz.course,
    )
    return build_attempt_session_payload(attempt)


@api.get("/quizzes/{quiz_id}/attempts/my", response=List[QuizAttemptHistoryOut], auth=apiAuth, tags=["Assessments"])
@is_student
def my_quiz_attempt_history(request, quiz_id: int):
    """Riwayat attempt quiz milik student berikut skor dan status kelulusan."""
    rate_limit(request)
    quiz = get_object_or_404(Quiz.objects.select_related("course"), id=quiz_id)
    if not Enrollment.objects.filter(student=request.user, course=quiz.course).exists():
        raise HttpError(403, "Forbidden")
    return list(
        QuizAttempt.objects.filter(quiz=quiz, student=request.user).order_by("-started_at")
    )


@api.post("/quiz-attempts/{attempt_id}/submit", response=QuizAttemptResultOut, auth=apiAuth, tags=["Assessments"])
@is_student
def finish_quiz_attempt(request, attempt_id: int, data: QuizSubmitIn):
    """Submit jawaban quiz, hitung skor otomatis, cek passing grade, dan keluarkan certificate jika syarat course terpenuhi."""
    rate_limit(request)
    attempt = get_object_or_404(
        QuizAttempt.objects.select_related("quiz", "quiz__course", "student", "enrollment"),
        id=attempt_id,
        student=request.user,
    )
    result = submit_quiz_attempt(attempt, [answer.dict() for answer in data.answers])
    invalidate_course_related_cache(attempt.quiz.course_id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="QUIZ_ATTEMPT_SUBMITTED",
        course_id=attempt.quiz.course_id,
        metadata={"quiz_id": attempt.quiz_id, "attempt_id": attempt.id, "score": result["score"]},
        user=request.user,
        course=attempt.quiz.course,
    )
    return result


@api.get("/certificates/my", response=List[CertificateOut], auth=apiAuth, tags=["Certificates"])
@is_student
def my_certificates(request):
    """Daftar certificate milik student yang sudah menyelesaikan course."""
    rate_limit(request)
    certificates = (
        Certificate.objects.filter(student=request.user)
        .select_related("course", "course__instructor", "course__category")
        .order_by("-issued_at")
    )
    return [serialize_certificate(request, certificate) for certificate in certificates]


@api.get("/certificates/{code}", response=CertificateOut, auth=apiAuth, tags=["Certificates"])
def get_certificate(request, code: str):
    """Lihat detail certificate. Pemilik certificate, instructor pemilik course, dan admin diperbolehkan mengakses."""
    rate_limit(request)
    certificate = get_object_or_404(
        Certificate.objects.select_related("course", "course__instructor", "course__category", "student"),
        code=code,
    )
    if request.user != certificate.student and not can_manage_course(request.user, certificate.course):
        raise HttpError(403, "Forbidden")
    return serialize_certificate(request, certificate)


@api.get("/certificates/{code}/pdf", auth=apiAuth, tags=["Certificates"])
def download_certificate_pdf(request, code: str):
    """Unduh certificate sebagai file PDF sederhana dengan kode verifikasi unik."""
    rate_limit(request)
    certificate = get_object_or_404(
        Certificate.objects.select_related("course", "student"),
        code=code,
    )
    if request.user != certificate.student and not can_manage_course(request.user, certificate.course):
        raise HttpError(403, "Forbidden")
    pdf_content = render_certificate_pdf(certificate)
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="certificate-{certificate.code}.pdf"'
    return response


@api.get("/certificates/verify/{code}", response=CertificateVerificationOut, tags=["Certificates"])
def verify_certificate(request, code: str):
    """Endpoint publik untuk verifikasi certificate berdasarkan kode unik."""
    rate_limit(request)
    certificate = get_object_or_404(
        Certificate.objects.select_related("course", "student"),
        code=code,
    )
    return {
        "code": certificate.code,
        "issued_at": certificate.issued_at,
        "final_score": round(certificate.final_score, 2),
        "student_name": certificate.student.get_full_name() or certificate.student.username,
        "course_name": certificate.course.name,
        "is_valid": True,
    }


@api.get("/courses/{course_id}/leaderboard", response=List[LeaderboardEntryOut], tags=["Assessments"])
def course_leaderboard(request, course_id: int):
    """Leaderboard course berdasarkan skor quiz terbaik, progress total, dan completion time."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_visibility(request, course)
    return build_leaderboard(course)


@api.post("/courses/{course_id}/export-report", response=MessageOut, auth=apiAuth, tags=["Courses"])
@is_instructor
def export_report(request, course_id: int):
    """Jalankan background task untuk mengekspor CSV progress enrollment pada course."""
    rate_limit(request)
    course = get_object_or_404(Course, id=course_id)
    require_course_management(request, course)
    export_course_report.delay(course_id)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="COURSE_EXPORT_REPORT",
        course_id=course.id,
        user=request.user,
        course=course,
    )
    return {"message": "Report export started, check Celery logs for details"}


@api.get("/analytics/activity-logs", response=List[ActivityLogOut], auth=apiAuth, tags=["Analytics"])
@is_instructor
def get_activity_logs(
    request,
    course_id: Optional[int] = None,
    action: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    """Lihat activity log dari MongoDB. Instructor hanya melihat course miliknya, admin melihat semua."""
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


@api.get("/analytics/learning", response=List[LearningAnalyticsOut], auth=apiAuth, tags=["Analytics"])
@is_instructor
def learning_analytics(request, course_id: Optional[int] = None, refresh: bool = False):
    """Ringkasan analytics pembelajaran yang dibangun dari koleksi MongoDB."""
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


@api.post("/analytics/learning/rebuild", response=MongoSyncOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def rebuild_learning_analytics(request, course_id: Optional[int] = None):
    """Bangun ulang koleksi analytics MongoDB dari activity logs."""
    rate_limit(request)
    result = sync_learning_analytics(course_id=course_id)
    return {
        "message": "Learning analytics collection synced",
        "synced_count": result["synced_count"],
    }


@api.patch("/analytics/activity-logs/review", response=MongoSyncOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def review_activity_logs(request, action: str = "COURSE_VIEW"):
    """Tandai activity log tertentu sebagai reviewed."""
    rate_limit(request)
    result = update_activity_logs(
        filters={"action": action},
        updates={"reviewed": True},
    )
    return {
        "message": "Activity logs updated",
        "synced_count": result["modified_count"],
    }


@api.delete("/analytics/activity-logs", response=MessageOut, auth=apiAuth, tags=["Analytics"])
@is_admin
def remove_activity_logs(request, action: str):
    """Hapus activity log MongoDB berdasarkan action."""
    rate_limit(request)
    deleted_count = delete_activity_logs(filters={"action": action})
    return {"message": f"Deleted {deleted_count} activity logs"}


@api.post("/tasks/demo-add", response=TaskQueuedOut, auth=apiAuth, tags=["Async Tasks"])
def queue_add_demo(request, data: TaskDemoIn):
    """Contoh endpoint untuk enqueue Celery task demo."""
    rate_limit(request)
    async_result = add_numbers.apply_async(args=[data.x, data.y], countdown=data.countdown)
    log_activity(
        user_id=request.user.id,
        user_role=request.user.role,
        action="TASK_DEMO_ADD_ENQUEUED",
        metadata={
            "task_id": async_result.id,
            "x": data.x,
            "y": data.y,
            "countdown": data.countdown,
        },
        user=request.user,
    )
    return {
        "message": "Task queued successfully",
        "task_id": async_result.id,
        "queue": "celery",
    }


@api.get("/tasks/{task_id}", response=TaskResultOut, auth=apiAuth, tags=["Async Tasks"])
def get_task_status(request, task_id: str):
    """Cek status task Celery berdasarkan task id."""
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
