from functools import wraps
from ninja.errors import HttpError
from typing import Callable, Any


def is_admin(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if request.user.role != "admin":
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper


def is_instructor(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if request.user.role not in ["instructor", "admin"]:
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper


def is_student(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(request, *args, **kwargs) -> Any:
        if not request.user.is_authenticated:
            raise HttpError(401, "Unauthorized")
        if request.user.role not in ["student", "admin"]:
            raise HttpError(403, "Forbidden")
        return func(request, *args, **kwargs)
    return wrapper