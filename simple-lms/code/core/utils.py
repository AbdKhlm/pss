from functools import wraps
from ninja.errors import HttpError
from typing import Callable, Any


def get_user_role(user) -> str:
    role = getattr(user, "role", "") or ""
    if role:
        return role

    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return "admin"

    return ""


def is_admin(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if get_user_role(request.user) != "admin":
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper


def is_instructor(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if get_user_role(request.user) not in ["instructor", "admin"]:
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper


def is_student(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if get_user_role(request.user) not in ["student", "admin"]:
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper
