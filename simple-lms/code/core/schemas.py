from typing import Optional, List
from ninja import Schema
from datetime import datetime


class TeacherOut(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str


class ContentOut(Schema):
    id: int
    title: str


class CourseOut(Schema):
    id: int
    name: str
    description: str
    price: int
    image: str
    teacher: TeacherOut
    created_at: datetime
    updated_at: datetime


class DetailCourseOut(CourseOut):
    contents: List[ContentOut] = []


class CourseIn(Schema):
    name: str
    description: str
    price: int
    category_id: Optional[int] = None


class CourseUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    category_id: Optional[int] = None


class UserOut(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    role: str


class UserRegisterIn(Schema):
    username: str
    first_name: str = ""
    last_name: str = ""
    email: str
    password: str
    role: str = "student"


class UserUpdateIn(Schema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class MessageOut(Schema):
    message: str


class EnrollmentOut(Schema):
    id: int
    course: CourseOut
    enrolled_at: datetime
    progress_percentage: int


class EnrollmentIn(Schema):
    course_id: int


class ProgressIn(Schema):
    lesson_id: int