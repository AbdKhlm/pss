from typing import List, Optional
from ninja import NinjaAPI, Query
from ninja.errors import HttpError
from ninja_simple_jwt.auth.views.api import mobile_auth_router
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth
from django.shortcuts import get_object_or_404
from courses.models import Course, Lesson, User, Category, Enrollment, Progress
from core.schemas import (
    CourseIn, CourseOut, DetailCourseOut,
    UserOut, UserRegisterIn, UserUpdateIn,
    MessageOut, EnrollmentOut, EnrollmentIn,
    ProgressIn
)
from core.utils import is_admin, is_instructor, is_student


# Inisialisasi API
api = NinjaAPI(title="Simple LMS API", version="1.0", description="REST API for Simple LMS")

# Register auth router dari ninja-simple-jwt
# Ini menyediakan endpoint /auth/sign-in dan /auth/token-refresh
api.add_router("/auth/", mobile_auth_router)

# Inisialisasi JWT auth handler
# Digunakan sebagai parameter auth= pada endpoint yang butuh authentication
apiAuth = HttpJwtAuth()


# ======================
# AUTH ENDPOINTS (Registration, Me, Update)
# ======================
@api.post('/auth/register', response=UserOut, tags=["Authentication"])
def register(request, data: UserRegisterIn):
    # Cek apakah username sudah digunakan
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")
    
    # Cek apakah email sudah digunakan
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email sudah digunakan")
    
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
    return new_user


@api.get('/auth/me', response=UserOut, auth=apiAuth, tags=["Authentication"])
def get_current_user(request):
    return request.user


@api.put('/auth/me', response=UserOut, auth=apiAuth, tags=["Authentication"])
def update_profile(request, data: UserUpdateIn):
    user = request.user
    for attr, value in data.dict(exclude_unset=True).items():
        setattr(user, attr, value)
    user.save()
    return user


# ======================
# COURSES ENDPOINTS (Public)
# ======================
@api.get('/courses', response=List[CourseOut], tags=["Courses"])
def list_courses(
    request,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    limit: int = 10,
    offset: int = 0
):
    courses = Course.objects.select_related("instructor", "category")
    if search:
        courses = courses.filter(name__icontains=search)
    if category_id:
        courses = courses.filter(category_id=category_id)
    # Fix: Assign teacher = instructor for CourseOut
    for course in courses:
        course.teacher = course.instructor
    return courses[offset:offset+limit]


@api.get('/courses/{course_id}', response=DetailCourseOut, tags=["Courses"])
def get_course(request, course_id: int):
    course = get_object_or_404(Course, id=course_id)
    course.teacher = course.instructor
    course.contents = [
        {"id": lesson.id, "title": lesson.title}
        for lesson in course.lessons.all()
    ]
    return course


# ======================
# COURSES ENDPOINTS (Protected)
# ======================
@api.post('/courses', response={201: CourseOut}, auth=apiAuth, tags=["Courses"])
@is_instructor
def create_course(request, data: CourseIn):
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
    return 201, course


@api.patch('/courses/{course_id}', response=CourseOut, auth=apiAuth, tags=["Courses"])
def update_course(request, course_id: int, data: CourseIn):
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
    return course


@api.delete('/courses/{course_id}', response={204: None}, auth=apiAuth, tags=["Courses"])
@is_admin
def delete_course(request, course_id: int):
    course = get_object_or_404(Course, id=course_id)
    course.delete()
    return 204, None


# ======================
# ENROLLMENTS ENDPOINTS
# ======================
@api.post('/enrollments', response={201: EnrollmentOut}, auth=apiAuth, tags=["Enrollments"])
@is_student
def enroll(request, data: EnrollmentIn):
    course = get_object_or_404(Course, id=data.course_id)
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        raise HttpError(400, "Already enrolled")
    enrollment = Enrollment.objects.create(
        student=request.user,
        course=course,
    )
    return 201, enrollment


@api.get('/enrollments/my-courses', response=List[EnrollmentOut], auth=apiAuth, tags=["Enrollments"])
@is_student
def my_enrollments(request):
    enrollments = Enrollment.objects.filter(student=request.user).select_related("course", "course__instructor")
    return enrollments


@api.post('/enrollments/{enrollment_id}/progress', response=MessageOut, auth=apiAuth, tags=["Enrollments"])
@is_student
def mark_lesson_complete(request, enrollment_id: int, data: ProgressIn):
    enrollment = get_object_or_404(Enrollment, id=enrollment_id, student=request.user)
    lesson = get_object_or_404(Lesson, id=data.lesson_id, course=enrollment.course)
    progress, created = Progress.objects.get_or_create(
        student=request.user,
        lesson=lesson,
        enrollment=enrollment,
        defaults={"completed": True},
    )
    if not created:
        progress.completed = True
        progress.save()
    return {"message": "Lesson marked as complete"}
