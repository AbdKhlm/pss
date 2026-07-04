# Simple LMS

Simple Learning Management System built with Django, PostgreSQL, Docker, Django Admin, and Django Ninja (with JWT Authentication via django-ninja-simple-jwt).

This project demonstrates:

- relational database design with Django ORM
- custom user roles (`admin`, `instructor`, `student`)
- course, lesson, enrollment, and progress management
- query optimization with `select_related`, `prefetch_related`, and annotations
- complete REST API with JWT Authentication and role-based authorization using Django Ninja

## Features

- Custom `User` model with role-based data
- Category hierarchy using self-referencing relation
- Course and lesson management
- Enrollment and lesson progress tracking
- Optimized queryset helpers for listing and dashboard use cases
- Django Admin configuration for core models
- Complete REST API under `/api/`
- JWT Authentication using `django-ninja-simple-jwt` (RSA-signed tokens)
- Role-based Access Control (RBAC) with decorators
- Automatic API documentation with Swagger UI
- Docker-based local development setup

## Tech Stack

- Django
- PostgreSQL
- Django Ninja
- Django Ninja Simple JWT (JWT Auth, RSA-signed)
- Gunicorn
- WhiteNoise
- Docker / Docker Compose

## Project Structure

```text
simple-lms/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── code/
    ├── manage.py
    ├── config/
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── core/
    │   ├── apiv1.py        # API routes with JWT auth and RBAC
    │   ├── schemas.py      # Pydantic schemas for request/response
    │   └── utils.py        # Role decorators (@is_admin, @is_instructor, @is_student)
    ├── courses/
    │   ├── admin.py
    │   ├── migrations/
    │   ├── models.py
    │   └── tests.py
    ├── templates/
    │   └── landing.html
    └── static/
```

## Data Model Summary

### Main entities

- `User`: extends Django `AbstractUser` and adds `role`
- `Category`: supports parent-child category hierarchy
- `Course`: belongs to an instructor and optional category
- `Lesson`: belongs to a course and has ordering per course
- `Enrollment`: links a student to a course
- `Progress`: tracks lesson completion for a student

### Relationship summary

| Model | Relation |
| --- | --- |
| `Course -> User` | `ForeignKey` |
| `Course -> Category` | `ForeignKey` |
| `Lesson -> Course` | `ForeignKey` |
| `Enrollment -> User` | `ForeignKey` |
| `Enrollment -> Course` | `ForeignKey` |
| `Progress -> Lesson` | `ForeignKey` |
| `Progress -> User` | `ForeignKey` |
| `Progress -> Enrollment` | `ForeignKey` |

## Running the Project

### 1. Start with Docker

```bash
docker-compose up --build -d
```

The `web` service automatically runs migrations and `collectstatic` before starting Gunicorn.

### 2. Access the application

- Home: `http://localhost:8000/`
- Django Admin: `http://localhost:8000/admin`
- API docs (Swagger UI): `http://localhost:8000/api/docs`

### 3. Create a superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

### 4. Run tests

```bash
docker-compose exec web python manage.py test
```

## REST API

The API is registered in [code/config/urls.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/config/urls.py) and implemented in [code/core/apiv1.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/core/apiv1.py).

### Base path

```text
/api/
```

### Available endpoints

#### Authentication

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | /api/auth/register | Register new user |
| POST | /api/auth/sign-in | Login (get access + refresh JWT tokens) |
| POST | /api/auth/token-refresh | Refresh access token |
| GET | /api/auth/me | Get current user (requires JWT) |
| PUT | /api/auth/me | Update current user profile (requires JWT) |

#### Courses (Public)

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | /api/courses | List courses with optional search/filter |
| GET | /api/courses/{id} | Get course detail with contents |

#### Courses (Protected)

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | /api/courses | Create course (requires `instructor` role) |
| PATCH | /api/courses/{id} | Update course (requires `instructor` owner or `admin`) |
| DELETE | /api/courses/{id} | Delete course (requires `admin` role) |

#### Enrollments (Protected)

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | /api/enrollments | Enroll to course (requires `student` role) |
| GET | /api/enrollments/my-courses | Get my enrolled courses (requires `student` role) |
| POST | /api/enrollments/{id}/progress | Mark lesson complete (requires `student` role) |

### Example requests and responses

#### Register user

```http
POST /api/auth/register
Content-Type: application/json
```

```json
{
  "username": "student01",
  "first_name": "Alice",
  "last_name": "Johnson",
  "email": "alice@example.com",
  "password": "strongpassword123",
  "role": "student"
}
```

#### Login (get JWT tokens)

```http
POST /api/auth/sign-in
Content-Type: application/json
```

```json
{
  "username": "student01",
  "password": "strongpassword123"
}
```

#### Get course detail (public)

```http
GET /api/courses/1/
```

```json
{
  "id": 1,
  "name": "Pemrograman Web",
  "description": "Belajar membuat aplikasi web",
  "price": 50000,
  "image": "",
  "teacher": {
    "id": 3,
    "username": "dosen01",
    "first_name": "Budi",
    "last_name": "Santoso",
    "email": "budi@example.com"
  },
  "created_at": "2026-07-04T04:19:08.971Z",
  "updated_at": "2026-07-04T04:19:08.971Z",
  "contents": [
    { "id": 1, "title": "Pengenalan Django" },
    { "id": 2, "title": "Instalasi dan Setup" },
    { "id": 3, "title": "Model dan Migration" }
  ]
}
```

#### Create course (protected: instructor)

```http
POST /api/courses/
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "name": "Machine Learning",
  "description": "Belajar ML dengan Python",
  "price": 75000,
  "category_id": 1
}
```

#### Enroll to course (protected: student)

```http
POST /api/enrollments/
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "course_id": 1
}
```

#### Mark lesson complete (protected: student)

```http
POST /api/enrollments/1/progress
Content-Type: application/json
Authorization: Bearer <access_token>
```

```json
{
  "lesson_id": 1
}
```

## Query Optimization

The project includes queryset helpers in [code/courses/models.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/courses/models.py):

- `Course.objects.for_listing()`
- `Enrollment.objects.for_student_dashboard()`

Examples of optimizations used:

- `select_related('instructor', 'category')`
- `prefetch_related('lessons')`
- `annotate(...)` for aggregated data

## Django Admin

Admin configuration is available in [code/courses/admin.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/courses/admin.py) and includes:

- searchable user, course, and enrollment data
- course filtering by category and instructor
- inline lesson editing inside courses
- progress percentage display for enrollments

## Important Files

- Models: [code/courses/models.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/courses/models.py)
- Admin: [code/courses/admin.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/courses/admin.py)
- API routes: [code/core/apiv1.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/core/apiv1.py)
- API schemas: [code/core/schemas.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/core/schemas.py)
- API decorators: [code/core/utils.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/core/utils.py)
- Project URLs: [code/config/urls.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/config/urls.py)
- Settings: [code/config/settings.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/config/settings.py)
- Docker config: [docker-compose.yml](file:///E:/SEMESTER%206/PSS/simple-lms/docker-compose.yml)

## Notes

- The active Django project used by Docker is the one under `code/`.
- The API documentation is served by Django Ninja at `http://localhost:8000/api/docs`.
- There is currently no fixture file committed in `code/fixtures/`.
