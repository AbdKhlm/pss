from datetime import datetime
from typing import List, Optional

from ninja import Field, Schema


class TeacherOut(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str


class CategoryOut(Schema):
    id: int
    name: str
    parent_id: Optional[int] = None


class ContentOut(Schema):
    id: int
    title: str


class LessonSummaryOut(Schema):
    id: int
    title: str
    order: int
    is_completed: bool = False


class LessonOut(Schema):
    id: int
    section_id: int
    title: str
    content: str
    order: int


class SectionOut(Schema):
    id: int
    title: str
    description: str
    order: int
    lessons: List[LessonSummaryOut] = []


class CourseOut(Schema):
    id: int
    name: str
    description: str
    price: int
    image: str
    level: str
    status: str
    teacher: TeacherOut
    category: Optional[CategoryOut] = None
    created_at: datetime
    updated_at: datetime
    average_rating: float = 0
    review_count: int = 0
    student_count: int = 0
    wishlist_count: int = 0


class DetailCourseOut(CourseOut):
    contents: List[ContentOut] = []
    curriculum: List[SectionOut] = []
    published_quiz_count: int = 0


class CourseIn(Schema):
    name: str = Field(..., description="Nama course.")
    description: str = Field(..., description="Deskripsi lengkap course.")
    price: int = Field(0, description="Harga course. Gunakan 0 untuk course gratis.")
    category_id: Optional[int] = Field(None, description="ID category course.")
    image: str = Field("", description="URL atau path gambar course.")
    level: str = Field("beginner", description="Level course: beginner, intermediate, advanced.")
    status: str = Field("draft", description="Status course: draft, published, archived.")


class CourseUpdateIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None
    category_id: Optional[int] = None
    image: Optional[str] = None
    level: Optional[str] = None
    status: Optional[str] = None


class CourseSectionIn(Schema):
    title: str
    description: str = ""
    order: int


class CourseSectionUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    order: Optional[int] = None


class LessonIn(Schema):
    section_id: int
    title: str
    content: str
    order: int


class LessonUpdateIn(Schema):
    section_id: Optional[int] = None
    title: Optional[str] = None
    content: Optional[str] = None
    order: Optional[int] = None


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
    role: str = Field(
        "student",
        description="Registrasi publik selalu disimpan sebagai student walaupun field ini dikirim.",
    )


class LoginIn(Schema):
    username: str = Field(..., description="Username akun yang sudah terdaftar.")
    password: str = Field(..., description="Password akun.")


class TokenPairOut(Schema):
    access: str = Field(
        ...,
        description="Gunakan token ini untuk endpoint yang membutuhkan autentikasi.",
    )
    refresh: str = Field(
        ...,
        description="Gunakan hanya untuk endpoint refresh token, bukan untuk endpoint protected biasa.",
    )


class UserUpdateIn(Schema):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None


class MessageOut(Schema):
    message: str


class ReviewIn(Schema):
    rating: int = Field(..., description="Nilai 1 sampai 5.")
    comment: str = Field("", description="Ulasan singkat student terhadap course.")


class ReviewOut(Schema):
    id: int
    rating: int
    comment: str
    created_at: datetime
    updated_at: datetime
    student: TeacherOut

    @staticmethod
    def resolve_student(obj):
        return obj.student


class WishlistOut(Schema):
    id: int
    created_at: datetime
    course: CourseOut


class SectionProgressLessonOut(Schema):
    id: int
    title: str
    order: int
    is_completed: bool


class SectionProgressOut(Schema):
    id: int
    title: str
    description: str
    order: int
    lesson_count: int
    completed_lessons: int
    progress_percentage: float
    lessons: List[SectionProgressLessonOut]


class QuizProgressOut(Schema):
    id: int
    title: str
    lesson_id: Optional[int] = None
    passing_grade: int
    attempt_limit: int
    best_score: Optional[float] = None
    is_passed: bool


class EnrollmentProgressOut(Schema):
    progress_percentage: float
    total_lessons: int
    completed_lessons: int
    total_quizzes: int
    passed_quizzes: int
    is_completed: bool
    completed_at: Optional[str] = None
    sections: List[SectionProgressOut]
    quizzes: List[QuizProgressOut]


class EnrollmentOut(Schema):
    id: int
    course: CourseOut
    enrolled_at: datetime
    progress_percentage: float
    is_completed: bool
    completed_at: Optional[str] = None


class EnrollmentIn(Schema):
    course_id: int


class ProgressIn(Schema):
    lesson_id: int


class DashboardOut(Schema):
    active_courses: List[EnrollmentOut]
    completed_courses: List[EnrollmentOut]
    wishlist_courses: List[CourseOut]
    recommendations: List[CourseOut]


class QuizOptionIn(Schema):
    text: str
    is_correct: bool = False
    order: Optional[int] = None


class QuizQuestionIn(Schema):
    prompt: str
    explanation: str = ""
    weight: int = 1
    order: Optional[int] = None
    options: List[QuizOptionIn]


class QuizIn(Schema):
    title: str
    description: str = ""
    instructions: str = ""
    lesson_id: Optional[int] = None
    passing_grade: int = 70
    attempt_limit: int = 3
    shuffle_questions: bool = True
    shuffle_options: bool = True
    is_published: bool = False
    questions: List[QuizQuestionIn]


class QuizUpdateIn(Schema):
    title: Optional[str] = None
    description: Optional[str] = None
    instructions: Optional[str] = None
    lesson_id: Optional[int] = None
    passing_grade: Optional[int] = None
    attempt_limit: Optional[int] = None
    shuffle_questions: Optional[bool] = None
    shuffle_options: Optional[bool] = None
    is_published: Optional[bool] = None
    questions: Optional[List[QuizQuestionIn]] = None


class QuizOptionOut(Schema):
    id: int
    text: str
    is_correct: bool
    order: int


class QuizOptionPlayOut(Schema):
    id: int
    text: str
    order: int


class QuizQuestionOut(Schema):
    id: int
    prompt: str
    explanation: str
    weight: int
    order: int
    options: List[QuizOptionOut]

    @staticmethod
    def resolve_options(obj):
        return list(obj.options.all())


class QuizQuestionPlayOut(Schema):
    id: int
    prompt: str
    explanation: str
    weight: int
    order: int
    options: List[QuizOptionPlayOut]


class QuizSummaryOut(Schema):
    id: int
    title: str
    description: str
    instructions: str
    lesson_id: Optional[int] = None
    course_id: int
    passing_grade: int
    attempt_limit: int
    shuffle_questions: bool
    shuffle_options: bool
    is_published: bool
    question_count: int
    total_points: int

    @staticmethod
    def resolve_question_count(obj):
        return obj.questions.count()

    @staticmethod
    def resolve_total_points(obj):
        return obj.total_points()


class QuizDetailOut(QuizSummaryOut):
    questions: List[QuizQuestionOut]

    @staticmethod
    def resolve_questions(obj):
        return list(obj.questions.all())


class QuizAnswerIn(Schema):
    question_id: int
    selected_option_id: Optional[int] = None


class QuizAttemptStartOut(Schema):
    attempt_id: int
    quiz_id: int
    quiz_title: str
    passing_grade: int
    attempt_limit: int
    status: str
    started_at: str
    questions: List[QuizQuestionPlayOut]


class QuizAttemptAnswerResultOut(Schema):
    question_id: int
    selected_option_id: Optional[int] = None
    correct_option_id: Optional[int] = None
    is_correct: bool
    earned_points: int


class QuizAttemptResultOut(Schema):
    attempt_id: int
    quiz_id: int
    score: float
    earned_points: int
    total_points: int
    is_passed: bool
    submitted_at: Optional[str] = None
    answers: List[QuizAttemptAnswerResultOut]
    certificate_code: Optional[str] = None


class QuizSubmitIn(Schema):
    answers: List[QuizAnswerIn]


class QuizAttemptHistoryOut(Schema):
    id: int
    status: str
    score: float
    is_passed: bool
    started_at: datetime
    submitted_at: Optional[datetime] = None


class CertificateOut(Schema):
    code: str
    issued_at: datetime
    final_score: float
    course: CourseOut
    verification_url: str


class CertificateVerificationOut(Schema):
    code: str
    issued_at: datetime
    final_score: float
    student_name: str
    course_name: str
    is_valid: bool


class LeaderboardEntryOut(Schema):
    rank: int
    student_id: int
    student_name: str
    best_quiz_score: float
    progress_percentage: float
    completed_at: Optional[str] = None
    completion_time_seconds: Optional[float] = None


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
