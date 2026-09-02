import json

from flask import Response

from helpers.api import ApiHandler, Request
from helpers import tamy_users


class TamyUsers(ApiHandler):
    @classmethod
    def requires_superadmin(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action") or "list").strip().lower()
        try:
            if action == "list":
                return {"ok": True, "users": tamy_users.list_users()}
            if action == "create":
                user = tamy_users.create_user(
                    input.get("username", ""), input.get("password", ""),
                    input.get("role", tamy_users.ROLE_USER), input.get("active", True),
                )
                return {"ok": True, "user": user, "users": tamy_users.list_users()}
            if action == "update":
                kwargs = {}
                if "role" in input:
                    kwargs["role"] = input.get("role")
                if "active" in input:
                    kwargs["active"] = input.get("active")
                if input.get("password"):
                    kwargs["password"] = input.get("password")
                user = tamy_users.update_user(input.get("username", ""), **kwargs)
                return {"ok": True, "user": user, "users": tamy_users.list_users()}
            if action == "delete":
                tamy_users.delete_user(input.get("username", ""))
                return {"ok": True, "users": tamy_users.list_users()}
            return _error("Unknown user action", 400)
        except ValueError as exc:
            return _error(str(exc), 400)


def _error(message: str, status: int) -> Response:
    return Response(response=json.dumps({"ok": False, "error": message}), status=status, mimetype="application/json")
