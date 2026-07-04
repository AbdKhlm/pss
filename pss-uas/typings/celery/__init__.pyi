from typing import Any, Callable, Generic, ParamSpec, TypeVar, overload


P = ParamSpec("P")
R = TypeVar("R")


class TaskResult:
    id: str


class Task(Generic[P, R]):
    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def delay(self, *args: P.args, **kwargs: P.kwargs) -> TaskResult: ...
    def apply_async(
        self,
        args: tuple[Any, ...] = ...,
        kwargs: dict[str, Any] | None = ...,
        countdown: int = ...,
    ) -> TaskResult: ...


@overload
def shared_task(fn: Callable[P, R], /) -> Task[P, R]: ...


@overload
def shared_task(*args: Any, **kwargs: Any) -> Callable[[Callable[P, R]], Task[P, R]]: ...
