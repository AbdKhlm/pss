import csv
import time
from io import StringIO

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail

from courses.models import Course, Enrollment
from courses.services import ensure_certificate_for_enrollment


@shared_task
def add_numbers(x, y):
    time.sleep(5)
    return {
        "operation": "add_numbers",
        "x": x,
        "y": y,
        "result": x + y,
    }


@shared_task
def send_enrollment_email(student_email, course_name):
    time.sleep(3)
    subject = f"Enrollment Confirmation for {course_name}"
    message = f"You have successfully enrolled in {course_name}!"
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL or "no-reply@simple-lms.local",
        recipient_list=[student_email],
        fail_silently=False,
    )
    return {"status": "sent", "recipient": student_email, "course_name": course_name}


@shared_task
def generate_certificate(student_id, course_id):
    time.sleep(2)
    enrollment = Enrollment.objects.filter(student_id=student_id, course_id=course_id).first()
    if enrollment is None:
        return {
            "status": "skipped",
            "reason": "enrollment_not_found",
            "student_id": student_id,
            "course_id": course_id,
        }

    certificate = ensure_certificate_for_enrollment(enrollment)
    if certificate is None:
        return {
            "status": "skipped",
            "reason": "course_not_completed",
            "student_id": student_id,
            "course_id": course_id,
        }

    return {
        "status": "done",
        "student_id": student_id,
        "course_id": course_id,
        "certificate_code": certificate.code,
    }


@shared_task
def update_course_statistics():
    print("Updating course statistics...")
    courses = Course.objects.all()
    for course in courses:
        # Update enrollment count
        enrollment_count = course.enrollments.count()
        print(f"Course {course.id} has {enrollment_count} enrollments")
    return {"status": "done", "courses_updated": courses.count()}


@shared_task
def export_course_report(course_id):
    course = Course.objects.get(id=course_id)
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Student ID", "Student Username", "Enrollment Date", "Progress (%)"])
    for enrollment in course.enrollments.all():
        progress = enrollment.progress_percentage()
        writer.writerow([
            enrollment.student.id,
            enrollment.student.username,
            enrollment.enrolled_at,
            progress
        ])

    report_content = output.getvalue()
    output.close()

    print(f"Course report for course {course_id} generated.")
    return report_content
