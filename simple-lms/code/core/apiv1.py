
from typing import List, Optional
from ninja import NinjaAPI
from ninja.errors import HttpError
from courses.models import Course, Lesson, User
from core.schemas import (
    CourseIn, CourseOut, DetailCourseOut,
    TeacherOut, ContentOut
)


api = NinjaAPI(
    title="Simple LMS API",
    version="1.0",
    description="REST API for Simple LMS",
)


# Helper function
def get_object_or_404_helper(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        raise HttpError(404, f"{model.__name__} not found")


# ======================
# COURSES ENDPOINTS
# ======================
@api.get("/courses/", response=List[CourseOut], tags=["Courses"])
def list_courses(request, search: Optional[str] = None):
    """List all courses, optionally filter by search term in name"""
    courses = Course.objects.select_related("instructor")
    if search:
        courses = courses.filter(name__icontains=search)
    
    # Create Pydantic instances manually
    result = []
    for course in courses:
        result.append(CourseOut(
            id=course.id,
            name=course.name,
            description=course.description,
            price=course.price,
            image=course.image,
            teacher=TeacherOut(
                id=course.instructor.id,
                username=course.instructor.username,
                first_name=course.instructor.first_name,
                last_name=course.instructor.last_name,
                email=course.instructor.email,
            ),
            created_at=course.created_at,
            updated_at=course.updated_at,
        ))
    
    return result


@api.get("/courses/{course_id}/", response=DetailCourseOut, tags=["Courses"])
def get_course(request, course_id: int):
    """Get details of a single course including its contents (lessons)"""
    course = get_object_or_404_helper(Course, id=course_id)
    
    # Create Pydantic instance manually
    return DetailCourseOut(
        id=course.id,
        name=course.name,
        description=course.description,
        price=course.price,
        image=course.image,
        teacher=TeacherOut(
            id=course.instructor.id,
            username=course.instructor.username,
            first_name=course.instructor.first_name,
            last_name=course.instructor.last_name,
            email=course.instructor.email,
        ),
        created_at=course.created_at,
        updated_at=course.updated_at,
        contents=[
            ContentOut(id=lesson.id, name=lesson.title)
            for lesson in course.lessons.all()
        ],
    )


@api.post("/courses/", response={201: CourseOut}, tags=["Courses"])
def create_course(request, data: CourseIn):
    """Create a new course (teacher hardcoded to first user)"""
    instructor = User.objects.first()
    if not instructor:
        raise HttpError(400, "No teacher found")
    
    course = Course.objects.create(
        name=data.name,
        description=data.description,
        price=data.price,
        instructor=instructor,
    )
    
    return 201, CourseOut(
        id=course.id,
        name=course.name,
        description=course.description,
        price=course.price,
        image=course.image,
        teacher=TeacherOut(
            id=instructor.id,
            username=instructor.username,
            first_name=instructor.first_name,
            last_name=instructor.last_name,
            email=instructor.email,
        ),
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@api.put("/courses/{course_id}/", response=CourseOut, tags=["Courses"])
def update_course(request, course_id: int, data: CourseIn):
    """Update an existing course"""
    course = get_object_or_404_helper(Course, id=course_id)
    
    course.name = data.name
    course.description = data.description
    course.price = data.price
    course.save()
    
    return CourseOut(
        id=course.id,
        name=course.name,
        description=course.description,
        price=course.price,
        image=course.image,
        teacher=TeacherOut(
            id=course.instructor.id,
            username=course.instructor.username,
            first_name=course.instructor.first_name,
            last_name=course.instructor.last_name,
            email=course.instructor.email,
        ),
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


@api.delete("/courses/{course_id}/", response={204: None}, tags=["Courses"])
def delete_course(request, course_id: int):
    """Delete a course"""
    course = get_object_or_404_helper(Course, id=course_id)
    course.delete()
    return 204, None
