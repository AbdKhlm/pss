from typing import Any


class AsyncResult:
    id: str
    status: str
    result: Any

    def __init__(self, task_id: str) -> None: ...
    def ready(self) -> bool: ...
    def successful(self) -> bool: ...
