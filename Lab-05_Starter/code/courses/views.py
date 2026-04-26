"""
Views untuk Simple LMS - Lab 05: Optimasi Database

File ini dibagi menjadi 3 bagian:

  BAGIAN 1 - Views dengan N+1 Problem
    Gunakan Django Silk (http://localhost:8000/silk/) untuk mengamati
    jumlah query yang dihasilkan oleh setiap endpoint.

  BAGIAN 2 - Views Teroptimasi (Referensi Solusi)
    Bandingkan jumlah query di Silk setelah mengakses endpoint ini.

  BAGIAN 3 - Statistik
    Contoh penggunaan aggregate() untuk kalkulasi di level database.

Petunjuk Lab:
  1. Jalankan python manage.py seed_data untuk mengisi data
  2. Akses endpoint BAGIAN 1, amati jumlah query di Silk
  3. Coba optimalkan sendiri sebelum melihat BAGIAN 2
  4. Bandingkan hasilnya
"""

from django.db.models import Avg, Count, Max, Min, Prefetch
from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import Comment, Course, CourseContent, CourseMember
from silk.profiling.profiler import silk_profile


# ---- Pasangan 1: Course + Teacher ----
@silk_profile(name='Course List Baseline')
def course_list_baseline(request):
    data = []
    courses = Course.objects.all()  # 1 query ambil semua course

    for course in courses:
        data.append({
            "id": course.id,
            "name": course.name,
            "teacher": course.teacher.username  # ✅ pakai username, bukan name
        })
        # Setiap iterasi memicu 1 query SELECT * FROM auth_user WHERE id = ?

    return JsonResponse(data, safe=False)


# OPTIMIZED
@silk_profile(name='Course List Optimized')
def course_list_optimized(request):
    data = []
    courses = Course.objects.select_related('teacher').all()  # 1 query dengan JOIN

    for course in courses:
        data.append({
            "id": course.id,
            "name": course.name,
            "teacher": course.teacher.username  # ✅ sudah ada di cache
        })

    return JsonResponse(data, safe=False)

# ---- Pasangan 2: Course Detail (Members + Content + Comments) ----

@silk_profile(name='Course Detail Baseline')
def course_detail_baseline(request):
    """BASELINE: N+1 problem"""
    data = []
    courses = Course.objects.all()

    for course in courses:
        # ✅ Perbaiki: pakai coursemember_set (bukan members)
        members = [m.user_id.username for m in course.coursemember_set.all()]
        contents = []

        # ✅ Perbaiki: pakai coursecontent_set (bukan contents)
        for content in course.coursecontent_set.all():
            comment_count = content.comment_set.count()  # ✅ pakai comment_set

            contents.append({
                "title": content.name,  # ✅ field 'name' bukan 'title'
                "comments": comment_count
            })

        data.append({
            "course": course.name,
            "members": members,
            "contents": contents
        })

    return JsonResponse(data, safe=False)



# OPTIMIZED
@silk_profile(name='Course Detail Optimized')
def course_detail_optimized(request):
    """OPTIMIZED: prefetch_related"""
    data = []

    courses = Course.objects.prefetch_related(
        'coursemember_set',           # untuk members
        'coursemember_set__user_id',  # untuk user dari member
        'coursecontent_set',          # untuk contents
        'coursecontent_set__comment_set'  # untuk comments per content
    )

    for course in courses:
        members = [m.user_id.username for m in course.coursemember_set.all()]
        contents = []

        for content in course.coursecontent_set.all():
            contents.append({
                "title": content.name,
                "comments": content.comment_set.count()  # sudah diprefetch
            })

        data.append({
            "course": course.name,
            "members": members,
            "contents": contents
        })

    return JsonResponse(data, safe=False)


# SUPER OPTIMIZED (pakai annotate)
@silk_profile(name='Course Detail Super Optimized')
def course_detail_super_optimized(request):
    """SUPER OPTIMIZED: prefetch_related + annotate"""
    data = []

    # Annotate setiap content dengan jumlah komentar
    # Gunakan 'comment' (bukan 'comment_set') karena itu adalah related name
    courses = Course.objects.prefetch_related(
        'coursemember_set',
        'coursemember_set__user_id',
        Prefetch(
            'coursecontent_set',
            queryset=CourseContent.objects.annotate(
                total_comments=Count('comment')  # ✅ perbaiki: 'comment' bukan 'comment_set'
            )
        )
    )

    for course in courses:
        members = [m.user_id.username for m in course.coursemember_set.all()]
        contents = [
            {
                "title": content.name,
                "comments": content.total_comments
            }
            for content in course.coursecontent_set.all()
        ]

        data.append({
            "course": course.name,
            "members": members,
            "contents": contents
        })

    return JsonResponse(data, safe=False)

# ---- Pasangan 3: Statistik Course ----

@silk_profile(name='Course Stats Baseline')
def course_stats_baseline(request):
    """BASELINE: N+1 problem (tanpa annotate)"""
    data = []
    courses = Course.objects.all()

    for course in courses:
        # ✅ Perbaiki: pakai coursemember_set (bukan members)
        total_members = course.coursemember_set.count()
        # ✅ Perbaiki: pakai coursecontent_set (bukan contents)
        total_contents = course.coursecontent_set.count()

        data.append({
            "course": course.name,
            "members": total_members,
            "contents": total_contents
        })

    return JsonResponse(data, safe=False)


# OPTIMIZED
@silk_profile(name='Course Stats Optimized')
def course_stats_optimized(request):
    """OPTIMIZED: menggunakan annotate (1 query untuk semua course)"""
    courses = Course.objects.annotate(
        total_members=Count('coursemember'),    # ✅ pakai coursemember_set
        total_contents=Count('coursecontent')   # ✅ pakai coursecontent_set
    )

    data = [
        {
            "course": course.name,
            "members": course.total_members,
            "contents": course.total_contents
        }
        for course in courses
    ]

    return JsonResponse(data, safe=False)

@silk_profile(name='Bulk Create Courses')
def bulk_create_courses(request):
    teacher = User.objects.first()  # ambil user pertama

    if not teacher:
        return JsonResponse({"error": "No user found"})

    courses = [
        Course(
            name=f"Course {i}",
            description="Bulk data",
            teacher=teacher
        )
        for i in range(50)
    ]

    Course.objects.bulk_create(courses)

    return JsonResponse({"message": "Courses created"})


@silk_profile(name='Bulk Create Members')
def bulk_create_members(request):
    course = Course.objects.first()
    users = User.objects.all()[:10]

    if not course:
        return JsonResponse({"error": "No course found"})

    members = [
        CourseMember(course=course, user=user)
        for user in users
    ]

    CourseMember.objects.bulk_create(members)

    return JsonResponse({"message": "Bulk insert success"})


@silk_profile(name='Bulk Update Courses')
def bulk_update_courses(request):
    courses = Course.objects.all()

    for c in courses:
        c.name = c.name + " Updated"

    Course.objects.bulk_update(courses, ['name'])

    return JsonResponse({"message": "Courses updated"})

@silk_profile(name='Course Aggregate Stats')
def course_aggregate_stats(request):
    from django.db.models import Avg, Count, Max, Min, Sum
    
    stats = Course.objects.aggregate(
        total_courses=Count('id'),
        avg_price=Avg('price'),
        max_price=Max('price'),
        min_price=Min('price'),
        total_revenue=Sum('price'),
    )
    return JsonResponse(stats)