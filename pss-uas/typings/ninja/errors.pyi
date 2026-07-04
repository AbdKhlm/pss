class HttpError(Exception):
    status_code: int
    message: str

    def __init__(self, status_code: int, message: str) -> None: ...
