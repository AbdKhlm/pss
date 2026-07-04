# Simple LMS

Simple Learning Management System built with Django, PostgreSQL, Docker, Django Admin, and Django Ninja.

This project demonstrates:

- relational database design with Django ORM
- custom user roles (`admin`, `instructor`, `student`)
- course, lesson, enrollment, and progress management
- query optimization with `select_related`, `prefetch_related`, and annotations
- basic REST API implementation with Django Ninja

## Features

- Custom `User` model with role-based data
- Category hierarchy using self-referencing relation
- Course and lesson management
- Enrollment and lesson progress tracking
- Optimized queryset helpers for listing and dashboard use cases
- Django Admin configuration for core models
- Basic REST API under `/api/v1/`
- Docker-based local development setup

## Tech Stack

- Django
- PostgreSQL
- Django Ninja
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
├── manage.py
└── code/
    ├── manage.py
    ├── config/
    │   ├── settings.py
    │   ├── urls.py
    │   └── wsgi.py
    ├── core/
    │   ├── apiv1.py
    │   └── schemas.py
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
docker-compose up --build
```

The `web` service automatically runs migrations and `collectstatic` before starting Gunicorn.

### 2. Access the application

- Home: `http://localhost:8000/`
- Django Admin: `http://localhost:8000/admin`
- API docs: `http://localhost:8000/api/v1/docs`

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
/api/v1/
```

### Available endpoints

- `GET /api/v1/courses/`
- `GET /api/v1/courses/{course_id}/`
- `POST /api/v1/courses/`
- `PUT /api/v1/courses/{course_id}/`
- `DELETE /api/v1/courses/{course_id}/`

### Example request and response

#### Get course detail

```http
GET /api/v1/courses/2/
```

```json
{
  "id": 2,
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
    { "id": 1, "name": "Pengenalan Django" },
    { "id": 2, "name": "Instalasi dan Setup" },
    { "id": 3, "name": "Model dan Migration" }
  ]
}
```

#### Create course

```http
POST /api/v1/courses/
Content-Type: application/json
```

```json
{
  "name": "Machine Learning",
  "description": "Belajar ML dengan Python",
  "price": 75000
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
- Project URLs: [code/config/urls.py](file:///E:/SEMESTER%206/PSS/simple-lms/code/config/urls.py)
- Docker config: [docker-compose.yml](file:///E:/SEMESTER%206/PSS/simple-lms/docker-compose.yml)

## Notes

- The active Django project used by Docker is the one under `code/`.
- The API documentation is served by Django Ninja at `http://localhost:8000/api/v1/docs`.
- There is currently no fixture file committed in `code/fixtures/`.
