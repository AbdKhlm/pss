from pymongo import MongoClient
from django.conf import settings


def get_mongo_db():
    client = MongoClient(settings.MONGODB_URI)
    return client[settings.MONGODB_DB_NAME]


def log_activity(user_id, user_role, action, course_id=None, lesson_id=None, metadata=None):
    db = get_mongo_db()
    activity = {
        "user_id": user_id,
        "user_role": user_role,
        "action": action,
        "course_id": course_id,
        "lesson_id": lesson_id,
        "metadata": metadata or {},
        "created_at": None,
    }
    return db.activity_log.insert_one(activity).inserted_id


def get_learning_analytics(course_id=None):
    db = get_mongo_db()
    pipeline = []
    if course_id:
        pipeline.append({"$match": {"course_id": course_id}})
    pipeline.extend([
        {"$group": {
            "_id": "$course_id",
            "total_actions": {"$sum": 1},
            "unique_users": {"$addToSet": "$user_id"}
        }},
        {"$project": {
            "_id": 1,
            "total_actions": 1,
            "unique_user_count": {"$size": "$unique_users"}
        }}
    ])
    return list(db.activity_log.aggregate(pipeline))
