# 🎓 Simple LMS (Django ORM)

Simple Learning Management System (LMS) berbasis **Django ORM** yang mendemonstrasikan:

* Desain database relasional
* Implementasi model dengan berbagai relasi
* Optimasi query (`select_related`, `prefetch_related`)
* Integrasi Django Admin
* Demonstrasi N+1 problem vs optimized query

---

# 🚀 Features

* 👤 Custom User dengan role (admin, instructor, student)
* 🗂️ Category hierarchy (self-referencing)
* 📚 Course & Lesson (ordered content)
* 🧾 Enrollment system (unique constraint)
* 📈 Progress tracking per lesson
* ⚡ Query optimization (efficient ORM usage)
* 🛠️ Django Admin interface
* 🧪 Unit testing
* 📦 Initial data fixtures

---

# 🏗️ Project Structure

```
simple-lms/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── code/
    ├── manage.py
    ├── lms/
    ├── courses/
    │   ├── models.py
    │   ├── admin.py
    │   ├── tests.py
    │   └── migrations/
    └── fixtures/
        └── initial_data.json
```

---

# 🧠 Database Design

## 📌 Entity Relationship

* **User**

  * role: admin / instructor / student

* **Category**

  * self-referencing (parent-child)

* **Course**

  * belongs to instructor (User)
  * belongs to Category

* **Lesson**

  * belongs to Course
  * ordered

* **Enrollment**

  * many-to-many (User ↔ Course)

* **Progress**

  * track lesson completion per student

---

## 🔗 Relationships Summary

| Model                      | Relation                     |
| -------------------------- | ---------------------------- |
| Course → User              | ForeignKey                   |
| Course → Category          | ForeignKey                   |
| Lesson → Course            | ForeignKey                   |
| Enrollment → User & Course | Many-to-Many (through model) |
| Progress → Lesson & User   | ForeignKey                   |

---

# ⚙️ Setup & Installation

## 1. Clone Repository

```bash
git clone <your-repo-url>
cd simple-lms
```

---

## 2. Run with Docker

```bash
docker-compose up --build
```

---

## 3. Apply Migration

```bash
docker-compose exec web python manage.py migrate
```

---

## 4. Load Initial Data

```bash
docker-compose exec web python manage.py loaddata fixtures/initial_data.json
```

---

## 5. Create Superuser

```bash
docker-compose exec web python manage.py createsuperuser
```

---

## 6. Access Admin

```
http://localhost:8000/admin
```

---

# ⚡ Query Optimization

## ❌ N+1 Problem

```python
courses = Course.objects.all()

for c in courses:
    print(c.instructor.username)
```

➡️ Menghasilkan banyak query (1 + N)

---

## ✅ Optimized Query

```python
courses = Course.objects.select_related('instructor')

for c in courses:
    print(c.instructor.username)
```

➡️ Hanya 1 query

---

## 🚀 Custom QuerySet

### Course Listing

```python
Course.objects.for_listing()
```

Optimasi:

* `select_related('instructor', 'category')`
* `prefetch_related('lessons')`
* `annotate(lesson_count, student_count)`

---

### Student Dashboard

```python
Enrollment.objects.for_student_dashboard()
```

Optimasi:

* join course & instructor
* prefetch lessons & progress
* annotate progress

---

# 🛠️ Django Admin Features

* 📊 Informative list display
* 🔍 Search functionality
* 🎯 Filtering (role, category, instructor)
* 🧩 Inline Lesson editing
* 📈 Progress percentage display

---

# 🧪 Testing

Run tests:

```bash
docker-compose exec web python manage.py test
```

Coverage:

* Model relationships
* Unique constraints
* Progress calculation
* QuerySet functionality

---

# 📦 Fixtures

File:

```
fixtures/initial_data.json
```

Berisi:

* Sample user
* Category
* Course
* Lesson
* Enrollment

---

# 📚 Key Concepts Implemented

* Object Relational Mapping (ORM)
* Database normalization
* Query optimization
* Aggregation (`annotate`)
* Reverse relationship handling
* Indexing & constraints

---

# 🎯 Learning Objectives Achieved

✅ Database schema design
✅ Django ORM implementation
✅ Query optimization
✅ Admin configuration
✅ Data migration & fixtures
✅ Query performance comparison

---

# 📊 Query Comparison (Example)

| Scenario  | Query Count |
| --------- | ----------- |
| N+1 Query | ~100+       |
| Optimized | ~1–3        |

---

# 🚀 Future Improvements

* REST API (Django REST Framework)
* Authentication (JWT)
* Course progress UI
* Caching (Redis)
* Pagination

---

# 👨‍💻 Author

* Name: Abdul Khalim
* Course: Pemrograman Sisi Server
* Assignment: Django ORM - Simple LMS

---

# 📌 Notes

Project ini dibuat untuk tujuan pembelajaran dan demonstrasi konsep Django ORM, khususnya:

* Relasi database
* Optimasi query
* Praktik best practices Django

---
