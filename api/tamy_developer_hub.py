import json

from flask import Response

from helpers.api import ApiHandler, Request
from helpers import tamy_developer_hub as hub


class TamyDeveloperHub(ApiHandler):
    @classmethod
    def requires_superadmin(cls) -> bool:
        return True

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = str(input.get("action") or "state").strip().lower()
        try:
            if action == "state":
                return {"ok": True, "state": hub.get_state()}
            if action == "refresh":
                hub._fetch_remote()
                return {"ok": True, "state": hub.get_state()}
            if action == "connect":
                connection = hub.connect_github(str(input.get("token") or ""))
                return {"ok": True, "connection": connection, "state": hub.get_state()}
            if action == "disconnect":
                hub.disconnect_github()
                return {"ok": True, "state": hub.get_state()}
            if action == "branches":
                return {"ok": True, "branches": hub.get_github_branches()}
            if action == "review_push":
                review = hub.review_push(
                    input.get("paths") or [],
                    str(input.get("message") or ""),
                )
                return {"ok": True, "review": review}
            if action == "push":
                return hub.push_reviewed(
                    input.get("paths") or [],
                    str(input.get("message") or ""),
                    str(input.get("review_id") or ""),
                )
            if action == "pull":
                return hub.pull_fast_forward()
            if action == "sync":
                return hub.sync_two_way()
            if action == "cleanup":
                return hub.cleanup_repo()
            if action == "logs":
                return {"ok": True, "operations": hub.get_operations()}
            return _error("Unknown Developer Hub action.", 400, "unknown_action")
        except hub.DeveloperHubError as exc:
            hub.record_event(action, "error", exc.message)
            return _error(exc.message, exc.status, exc.code)
        except Exception:
            hub.record_event(action, "error", "Unexpected Developer Hub error")
            return _error("Developer Hub could not complete the request.", 500, "unexpected_error")


def _error(message: str, status: int, code: str) -> Response:
    return Response(
        response=json.dumps({"ok": False, "error": message, "code": code}),
        status=status,
        mimetype="application/json",
    )
