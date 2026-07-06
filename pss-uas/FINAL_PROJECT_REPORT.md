# FINAL PROJECT REPORT - Simple LMS Extended

## Identitas

- Nama: Abdul Khalim
- NIM: A11.2023.15327
- Kelas: Pemrograman Sisi Server - A11.4618
- URL Repository: https://github.com/AbdKhlm/pss/tree/ba384b63592e00ddbc2691e9661771beab76f9e6/pss-uas

## Deskripsi Project

Project ini merupakan pengembangan backend **Simple LMS Extended** berbasis **Django**, **Django Ninja**, **PostgreSQL**, **JWT Authentication**, **MongoDB**, **Redis**, dan **Celery**. Sistem dikembangkan untuk mendukung kebutuhan pembelajaran online yang lebih lengkap dibanding Simple LMS dasar, dengan fokus utama pada peningkatan pengalaman student dan instructor, terutama pada fitur pencarian course, review dan wishlist, curriculum terstruktur, dashboard student, quiz, scoring otomatis, certificate, serta dokumentasi dan pengujian API.

Selain fitur inti LMS, project ini juga dilengkapi dengan layanan pendukung seperti activity logging dan analytics berbasis MongoDB, asynchronous task menggunakan Celery dan RabbitMQ, rate limiting, serta dokumentasi endpoint melalui Swagger/OpenAPI.

## Fitur Dasar yang Sudah Berjalan

Fitur dasar yang sudah tersedia dan dapat dijalankan:

- Docker Compose untuk menjalankan service backend dan service pendukung.
- Database PostgreSQL beserta migration.
- JWT Authentication untuk login API.
- Role-based access control untuk `admin`, `instructor`, dan `student`.
- Endpoint dasar `course`, `lesson`, `enrollment`, dan `progress`.
- Dokumentasi API melalui Swagger/OpenAPI di `/api/docs`.
- Struktur project dipisahkan menjadi `courses`, `core`, `config`, schema, service layer, test, dan admin.
- Konfigurasi sensitif dipisahkan melalui environment variable.
- Testing unit dan integration untuk fitur dasar dan fitur tambahan utama.

## Fitur Tambahan yang Dipilih

Fitur tambahan utama yang dipilih mengikuti **Paket 1 - LMS Experience** dan **Lampiran B - Assessment, Quiz, dan Certificate** pada dokumen tugas.

| No | Fitur | Kategori | Poin | Status |
| --- | --- | --- | ---: | --- |
| 1 | Search, filter, dan sorting course lanjutan | Paket 1 / Course & Learning Experience | 12 | Selesai |
| 2 | Rating, review, dan wishlist course | Paket 1 / Course & Learning Experience | 12 | Selesai |
| 3 | Curriculum dan progress belajar detail | Paket 1 / Course & Learning Experience | 15 | Selesai |
| 4 | Student dashboard | Paket 1 / Course & Learning Experience | 12 | Selesai |
| 5 | Quiz dan question bank | Lampiran B / Assessment, Quiz, dan Certificate | 15 | Selesai |
| 6 | Submit quiz dan scoring otomatis | Lampiran B / Assessment, Quiz, dan Certificate | 15 | Selesai |
| 7 | Attempt limit, passing grade, dan riwayat attempt | Lampiran B / Assessment, Quiz, dan Certificate | 15 | Selesai |
| 8 | Randomisasi quiz | Lampiran B / Assessment, Quiz, dan Certificate | 12 | Selesai |
| 9 | Certificate generation | Lampiran B / Assessment, Quiz, dan Certificate | 15 | Selesai |
| 10 | Certificate PDF dan verification | Lampiran B / Assessment, Quiz, dan Certificate | 18 | Selesai |
| 11 | Leaderboard course | Lampiran B / Assessment, Quiz, dan Certificate | 12 | Selesai |

**Total poin fitur tambahan yang diimplementasikan:** 153 poin  
**Catatan:** sesuai rubric, poin fitur tambahan tetap dibatasi maksimum 50 poin.

## Penjelasan Implementasi

### 1. Search, Filter, dan Sorting Course Lanjutan

Endpoint list course mendukung pencarian dan penyaringan berdasarkan:

- keyword pencarian,
- category,
- instructor,
- level,
- status,
- sorting `newest`, `popular`, dan `rating`.

Implementasi query dilakukan pada layer API dan service agar course mudah ditemukan dan tetap efisien untuk digunakan pada frontend atau client API.

### 2. Rating, Review, dan Wishlist

Student dapat:

- memberi review pada course,
- menghapus review miliknya,
- menambahkan course ke wishlist,
- melihat daftar wishlist miliknya.

Course juga menampilkan ringkasan rating dan jumlah review agar pengalaman discovery lebih baik.

### 3. Curriculum dan Progress Detail

Course dibagi ke dalam struktur:

- `Course`
- `CourseSection`
- `Lesson`

Perhitungan progress tidak lagi hanya berdasarkan jumlah lesson, tetapi juga mempertimbangkan completion yang lebih akurat. Endpoint progress menampilkan detail lesson yang selesai, section, dan ringkasan quiz yang terkait dengan enrollment.

### 4. Student Dashboard

Project menyediakan endpoint dashboard student yang menampilkan:

- course aktif,
- course selesai,
- progress per enrollment,
- rekomendasi course sederhana,
- ringkasan wishlist.

Dashboard ini ditujukan untuk memberikan pengalaman LMS yang lebih realistis dan informatif.

### 5. Quiz, Attempt, Scoring, dan Riwayat

Instructor dapat membuat quiz per course lengkap dengan:

- bank soal,
- pilihan jawaban,
- jawaban benar,
- bobot poin,
- passing grade,
- batas attempt,
- status publish.

Student dapat memulai attempt, mengerjakan quiz, submit jawaban, dan sistem akan menghitung skor otomatis lalu menyimpan hasil attempt beserta status lulus/gagal.

### 6. Randomisasi Quiz

Saat quiz dikerjakan, sistem dapat melakukan randomisasi:

- urutan soal,
- urutan opsi jawaban.

Randomisasi disimpan pada data attempt agar hasil submit tetap konsisten dengan urutan yang diterima oleh student.

### 7. Certificate, PDF, Verification, dan Leaderboard

Setelah student menyelesaikan course dan memenuhi syarat kelulusan, sistem akan:

- membuat certificate dengan kode unik,
- menampilkan detail certificate melalui endpoint API,
- menyediakan output PDF certificate,
- menyediakan endpoint verifikasi publik berdasarkan kode certificate.

Selain itu tersedia leaderboard course untuk menampilkan ranking student berdasarkan hasil quiz dan penyelesaian course.

### 8. Fitur Pendukung Tambahan

Selain fitur utama yang dipilih, project ini juga memiliki fitur pendukung berikut:

- activity logging ke MongoDB,
- learning analytics endpoint,
- asynchronous task menggunakan Celery,
- task status endpoint,
- Flower monitoring di Docker Compose,
- export report async,
- rate limiting untuk proteksi endpoint.

## Cara Menjalankan Project

### Menjalankan dengan Docker Compose

1. Buka terminal pada root project:

```bash
cd "e:\SEMESTER 6\PSS\pss-uas"
```

2. Pastikan file `.env` tersedia di root project.

3. Jalankan semua service:

```bash
docker compose up --build -d
```

4. Cek status service:

```bash
docker compose ps
```

5. Akses service utama:

- API / aplikasi: `http://127.0.0.1:8000`
- Swagger/OpenAPI: `http://127.0.0.1:8000/api/docs`
- Django Admin: `http://127.0.0.1:8000/admin`
- Flower: `http://127.0.0.1:5555`
- RabbitMQ Management: `http://127.0.0.1:15672`

6. Jika perlu melihat log:

```bash
docker compose logs -f web
docker compose logs -f celery-worker
```

### Menjalankan Testing

Automated test utama dapat dijalankan dengan:

```bash
.\.venv\Scripts\python code\manage.py test courses.tests core.tests -v 1
```

Hasil pengujian terakhir:

- `Ran 35 tests`
- `OK`

## Akun Demo

Akun demo yang digunakan pada environment pengujian Docker:

| Role | Username | Password | Keterangan |
| --- | --- | --- | --- |
| Admin | `docker_admin` | `DockerAdmin123!` | Digunakan untuk akses Django Admin dan validasi role admin |
| Instructor | `demo_instructor` | `DemoInstructor123!` | Digunakan untuk membuat dan mengelola course serta quiz |
| Student | `mahasiswa` | `mahasewa123` | Digunakan untuk enrollment, progress, quiz, dan certificate |

## Endpoint Penting

Daftar endpoint penting yang perlu diuji:

### Authentication

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `PUT /api/auth/me`

### Courses dan Curriculum

- `GET /api/courses`
- `GET /api/courses/{course_id}`
- `POST /api/courses`
- `POST /api/courses/{course_id}/sections`
- `POST /api/courses/{course_id}/lessons`
- `GET /api/lessons/{lesson_id}`

### Reviews dan Wishlist

- `GET /api/courses/{course_id}/reviews`
- `POST /api/courses/{course_id}/reviews`
- `DELETE /api/courses/{course_id}/reviews/me`
- `POST /api/wishlist`
- `GET /api/wishlist/my-courses`
- `DELETE /api/wishlist/{course_id}`

### Enrollment, Progress, dan Dashboard

- `POST /api/enrollments`
- `GET /api/enrollments/my-courses`
- `GET /api/enrollments/{enrollment_id}/progress`
- `POST /api/enrollments/{enrollment_id}/progress`
- `GET /api/dashboard/student`

### Assessment, Quiz, dan Certificate

- `POST /api/courses/{course_id}/quizzes`
- `GET /api/courses/{course_id}/quizzes`
- `GET /api/quizzes/{quiz_id}`
- `POST /api/quizzes/{quiz_id}/attempts/start`
- `GET /api/quizzes/{quiz_id}/attempts/my`
- `POST /api/quiz-attempts/{attempt_id}/submit`
- `GET /api/certificates/my`
- `GET /api/certificates/{code}`
- `GET /api/certificates/{code}/pdf`
- `GET /api/certificates/verify/{code}`
- `GET /api/courses/{course_id}/leaderboard`

### Analytics dan Async Tasks

- `GET /api/analytics/activity-logs`
- `GET /api/analytics/learning`
- `POST /api/analytics/learning/rebuild`
- `POST /api/tasks/demo-add`
- `GET /api/tasks/{task_id}`

## Screenshot / Bukti Pengujian

Screenshot atau bukti pengujian yang disarankan untuk dilampirkan:

1. `docker compose ps` saat semua service aktif.
2. Swagger/OpenAPI di `/api/docs`.
3. Login JWT berhasil pada endpoint `/api/auth/login`.
4. Django Admin berhasil diakses dengan role admin.
5. List course dengan search, filter, dan sorting.
6. Detail course yang menampilkan curriculum/section/lesson.
7. Review dan wishlist berhasil dibuat.
8. Enrollment berhasil.
9. Progress enrollment berhasil diperbarui.
10. Student dashboard menampilkan ringkasan data.
11. Instructor berhasil membuat quiz.
12. Student memulai attempt quiz.
13. Student submit quiz dan skor tampil.
14. History attempt quiz tampil.
15. Certificate list dan certificate detail tampil.
16. Certificate PDF berhasil diakses.
17. Endpoint verifikasi certificate berhasil.
18. Leaderboard course tampil.
19. Endpoint analytics berjalan.
20. Hasil automated testing menunjukkan semua test `OK`.

## Kendala dan Solusi

### 1. PDF spesifikasi terlalu besar untuk dibaca langsung

- **Kendala:** file PDF melebihi batas baca tool.
- **Solusi:** dilakukan ekstraksi teks halaman yang relevan secara terarah agar poin spesifikasi yang penting tetap bisa diacu dengan akurat.

### 2. Perluasan domain dari LMS dasar ke LMS Extended

- **Kendala:** model awal belum mencakup section, review, wishlist, quiz, certificate, dan leaderboard.
- **Solusi:** model, migration, fixture, admin, schema, service layer, dan endpoint API diperluas secara menyeluruh.

### 3. Konsistensi business logic dan struktur kode

- **Kendala:** jika semua logic ditaruh langsung di endpoint, codebase sulit dirawat.
- **Solusi:** logika utama dipisahkan ke service layer pada app `courses`.

### 4. Validasi dan otorisasi

- **Kendala:** setiap role memiliki hak akses berbeda, terutama untuk instructor, student, dan admin.
- **Solusi:** diterapkan decorator dan helper permission agar akses endpoint sesuai role dan ownership.

### 5. Pengujian fitur tambahan

- **Kendala:** fitur tambahan seperti quiz, certificate PDF, randomisasi quiz, dan discovery lanjutan perlu pembuktian pengujian yang memadai.
- **Solusi:** ditambahkan unit test dan integration test untuk membuktikan fitur berjalan sesuai spesifikasi.

### 6. Integrasi service tambahan

- **Kendala:** project menggunakan PostgreSQL, Redis, MongoDB, RabbitMQ, dan Celery sehingga setup lebih kompleks.
- **Solusi:** semua service disatukan pada Docker Compose agar environment demo dan pengujian lebih konsisten.
