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


class ActivitySnapshotOut(Schema):
    id: Optional[int] = None
    username: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    category_id: Optional[int] = None
    instructor_id: Optional[int] = None
    instructor_username: Optional[str] = None
    title: Optional[str] = None
    order: Optional[int] = None


class ActivityLogOut(Schema):
    id: str
    user_id: Optional[int] = None
    user_role: Optional[str] = None
    action: str
    course_id: Optional[int] = None
    lesson_id: Optional[int] = None
    metadata: dict = {}
    user_snapshot: Optional[ActivitySnapshotOut] = None
    course_snapshot: Optional[ActivitySnapshotOut] = None
    lesson_snapshot: Optional[ActivitySnapshotOut] = None
    created_at: str


class LearningAnalyticsOut(Schema):
    course_id: Optional[int] = None
    course_name: Optional[str] = None
    total_actions: int
    unique_user_count: int
    action_type_count: int
    last_activity_at: Optional[str] = None


class MongoSyncOut(Schema):
    message: str
    synced_count: int


class TaskDemoIn(Schema):
    x: int
    y: int
    countdown: int = 0


class TaskQueuedOut(Schema):
    message: str
    task_id: str
    queue: str


class TaskResultOut(Schema):
    task_id: str
    status: str
    ready: bool
    successful: bool
    result: Optional[dict | int | str | list] = None
