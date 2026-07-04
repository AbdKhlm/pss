from datetime import datetime
from typing import Any, cast

from bson import ObjectId
from django.conf import settings
from django.utils import timezone
from pymongo import DESCENDING, MongoClient


ACTIVITY_LOGS_COLLECTION = "activity_logs"
LEARNING_ANALYTICS_COLLECTION = "learning_analytics"


def get_mongo_db():
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    ensure_mongo_indexes(db)
    return db


def ensure_mongo_indexes(db):
    db[ACTIVITY_LOGS_COLLECTION].create_index([("created_at", DESCENDING)])
    db[ACTIVITY_LOGS_COLLECTION].create_index([("user_id", DESCENDING)])
    db[ACTIVITY_LOGS_COLLECTION].create_index([("course_id", DESCENDING)])
    db[ACTIVITY_LOGS_COLLECTION].create_index([("action", DESCENDING)])
    db[LEARNING_ANALYTICS_COLLECTION].create_index("course_id", unique=True)


def serialize_mongo_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize_mongo_value(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize_mongo_value(item) for key, item in value.items()}
    return value


def _build_user_snapshot(user):
    if not user:
        return None
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
    }


def _build_course_snapshot(course):
    if not course:
        return None
    return {
        "id": course.id,
        "name": course.name,
        "category_id": course.category_id,
        "instructor_id": course.instructor_id,
        "instructor_username": getattr(course.instructor, "username", None),
    }


def _build_lesson_snapshot(lesson):
    if not lesson:
        return None
    return {
        "id": lesson.id,
        "title": lesson.title,
        "order": lesson.order,
    }


def build_activity_document(
    user_id,
    user_role,
    action,
    course_id=None,
    lesson_id=None,
    metadata=None,
    user=None,
    course=None,
    lesson=None,
):
    return {
        "user_id": user_id,
        "user_role": user_role,
        "action": action,
        "course_id": course_id or getattr(course, "id", None),
        "lesson_id": lesson_id or getattr(lesson, "id", None),
        "metadata": metadata or {},
        "user_snapshot": _build_user_snapshot(user),
        "course_snapshot": _build_course_snapshot(course),
        "lesson_snapshot": _build_lesson_snapshot(lesson),
        "created_at": timezone.now(),
    }


def log_activity(
    user_id,
    user_role,
    action,
    course_id=None,
    lesson_id=None,
    metadata=None,
    user=None,
    course=None,
    lesson=None,
):
    db = get_mongo_db()
    activity = build_activity_document(
        user_id=user_id,
        user_role=user_role,
        action=action,
        course_id=course_id,
        lesson_id=lesson_id,
        metadata=metadata,
        user=user,
        course=course,
        lesson=lesson,
    )
    return db[ACTIVITY_LOGS_COLLECTION].insert_one(activity).inserted_id


def list_activity_logs(filters=None, limit=20, skip=0):
    db = get_mongo_db()
    query = filters or {}
    cursor = (
        db[ACTIVITY_LOGS_COLLECTION]
        .find(query)
        .sort("created_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return [serialize_mongo_value(document) for document in cursor]


def update_activity_logs(filters, updates, many=True, upsert=False):
    db = get_mongo_db()
    operator = {"$set": updates}
    if many:
        result = db[ACTIVITY_LOGS_COLLECTION].update_many(filters, operator, upsert=upsert)
    else:
        result = db[ACTIVITY_LOGS_COLLECTION].update_one(filters, operator, upsert=upsert)
    return {
        "matched_count": result.matched_count,
        "modified_count": result.modified_count,
        "upserted_id": serialize_mongo_value(result.upserted_id),
    }


def delete_activity_logs(filters, many=True):
    db = get_mongo_db()
    if many:
        result = db[ACTIVITY_LOGS_COLLECTION].delete_many(filters)
    else:
        result = db[ACTIVITY_LOGS_COLLECTION].delete_one(filters)
    return result.deleted_count


def record_daily_login(user_id):
    db = get_mongo_db()
    result = db[ACTIVITY_LOGS_COLLECTION].update_one(
        {"user_id": user_id, "action": "daily_login"},
        {
            "$set": {"last_login": timezone.now()},
            "$inc": {"login_count": 1},
        },
        upsert=True,
    )
    return {
        "matched_count": result.matched_count,
        "modified_count": result.modified_count,
        "upserted_id": serialize_mongo_value(result.upserted_id),
    }


def build_learning_analytics_pipeline(course_id=None):
    pipeline = []
    if course_id:
        pipeline.append({"$match": {"course_id": course_id}})

    pipeline.extend(
        [
            {
                "$group": {
                    "_id": "$course_id",
                    "course_name": {"$last": "$course_snapshot.name"},
                    "total_actions": {"$sum": 1},
                    "unique_users": {"$addToSet": "$user_id"},
                    "action_types": {"$addToSet": "$action"},
                    "last_activity_at": {"$max": "$created_at"},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "course_id": "$_id",
                    "course_name": 1,
                    "total_actions": 1,
                    "unique_user_count": {"$size": "$unique_users"},
                    "action_type_count": {"$size": "$action_types"},
                    "last_activity_at": 1,
                }
            },
            {"$sort": {"total_actions": -1, "course_id": 1}},
        ]
    )
    return pipeline


def aggregate_learning_analytics(course_id=None) -> list[dict[str, Any]]:
    db = get_mongo_db()
    pipeline = build_learning_analytics_pipeline(course_id=course_id)
    return cast(
        list[dict[str, Any]],
        [serialize_mongo_value(document) for document in db[ACTIVITY_LOGS_COLLECTION].aggregate(pipeline)],
    )


def sync_learning_analytics(course_id=None):
    db = get_mongo_db()
    analytics = aggregate_learning_analytics(course_id=course_id)
    synced = 0

    for document in analytics:
        db[LEARNING_ANALYTICS_COLLECTION].replace_one(
            {"course_id": document["course_id"]},
            document,
            upsert=True,
        )
        synced += 1

    return {
        "synced_count": synced,
        "course_id": course_id,
    }


def get_learning_analytics(course_id=None, refresh=False) -> list[dict[str, Any]]:
    db = get_mongo_db()

    if refresh:
        sync_learning_analytics(course_id=course_id)

    filters = {}
    if course_id:
        filters["course_id"] = course_id

    analytics = list(db[LEARNING_ANALYTICS_COLLECTION].find(filters).sort("total_actions", DESCENDING))
    if analytics:
        return cast(list[dict[str, Any]], [serialize_mongo_value(document) for document in analytics])

    return aggregate_learning_analytics(course_id=course_id)
