
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
    name: str


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
