from flask import request


def current_user() -> str:
    return request.headers.get("X-User-Email") or "dev@local"
