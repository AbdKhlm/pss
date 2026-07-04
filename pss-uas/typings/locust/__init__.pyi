from typing import Any, Callable, TypeVar, overload


F = TypeVar("F", bound=Callable[..., Any])


class HttpUser:
    client: Any


class between:
    def __init__(self, min_wait: int | float, max_wait: int | float) -> None: ...


@overload
def task(weight: int) -> Callable[[F], F]: ...


@overload
def task(fn: F) -> F: ...
