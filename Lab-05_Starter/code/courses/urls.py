from django.urls import path

from . import views

urlpatterns = [ path('baseline/courses/', views.course_list_baseline),
    path('optimized/courses/', views.course_list_optimized),

    path('baseline/detail/', views.course_detail_baseline),
    path('optimized/detail/', views.course_detail_optimized),
    path('optimized/detail-super/', views.course_detail_super_optimized),

    path('baseline/stats/', views.course_stats_baseline),
    path('optimized/stats/', views.course_stats_optimized),

    path('bulk/create-courses/', views.bulk_create_courses),
    path('bulk/create-members/', views.bulk_create_members),
    path('bulk/update-courses/', views.bulk_update_courses),

    path('lab/course-aggregate/', views.course_aggregate_stats),
    ]
