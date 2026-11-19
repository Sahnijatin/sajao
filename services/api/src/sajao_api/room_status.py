"""A room's job as the app sees it: one stage, a reason when it failed, how the room
was measured and, per design item, whether a fit check ran.

Pure: built from the room's rows and its latest design request. The app shows only
what this returns, so every failure carries a reason from the contract's list; a code
the list does not know is reported as `internal`.
"""

from typing import Any, get_args

from sajao_api.rooms import DesignRequest, Room, Stage
from sajao_schemas import SCHEMA_VERSION, RoomStatus, to_json_dict
from sajao_schemas.generated.v1 import RoomFailure

# The contract's reasons, read from the generated model so the two cannot drift.
REASONS: frozenset[str] = frozenset(get_args(RoomFailure.model_fields["reason"].annotation))
# Asking again (the same room or design request) may succeed for these; the others
# need a different capture or a different request.
RETRYABLE = frozenset({"internal", "timed_out", "render_failed"})
# Older codes the pipeline still writes, by the reason the contract names for them.
ALIASES = {"input_missing": "internal", "stage_failed": "internal"}

# Which room stage each pipeline row belongs to.
ROW_STAGE = {
    "measure": "reading",
    "inventory": "reading",
    "spec": "designing",
    "placement": "designing",
    "render": "rendering",
}
MEASURED = ("ar_measured", "taped")


def reason_of(detail: str | None) -> str:
    code = ALIASES.get(detail or "", detail or "internal")
    return code if code in REASONS else "internal"


def _live(rows: tuple[Stage, ...]) -> tuple[Stage, ...]:
    # A render row from before the render stage ran is never moved: leave it out.
    return tuple(r for r in rows if not (r.stage == "render" and r.status == "queued"))


def confidence_of(twin: dict[str, Any] | None) -> str | None:
    level = ((twin or {}).get("confidence") or {}).get("level")
    return level if level in ("estimated", "ar_measured", "taped") else None


def _items(designs: list[dict[str, Any]] | None, room_level: str | None) -> list[dict[str, Any]]:
    out = []
    for design in designs or []:
        level = design.get("measurement_level") or room_level
        for item in design.get("items", []):
            out.append(
                {
                    "design_id": design["id"],
                    "item_id": item["id"],
                    "fit_checked": level in MEASURED,
                }
            )
    return out


def room_stage(room: Room, request: DesignRequest | None) -> tuple[str, dict[str, Any] | None]:
    """The room's stage and, when it failed, why."""
    rows = room.stages + (_live(request.stages) if request is not None else ())
    failed = next((r for r in rows if r.status == "failed"), None)
    if failed is not None:
        reason = reason_of(failed.detail)
        return "failed", {
            "reason": reason,
            "stage": ROW_STAGE.get(failed.stage, "reading"),
            "retryable": reason in RETRYABLE,
        }
    if all(r.status == "queued" for r in room.stages):
        return "uploaded", None
    if any(r.status != "done" for r in room.stages) or room.space_twin is None:
        return "reading", None
    if request is None:
        return "designing", None
    pending = [r for r in _live(request.stages) if r.status != "done"]
    if not pending:
        return "ready", None
    return ROW_STAGE.get(pending[0].stage, "designing"), None


def room_status(room: Room, request: DesignRequest | None) -> dict[str, Any]:
    """The room status endpoint's body, validated against the contract."""
    stage, failure = room_stage(room, request)
    level = confidence_of(room.space_twin)
    read = room.space_twin is not None and all(r.status == "done" for r in room.stages)
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "id": room.room_id,
        "capture_id": room.capture_id,
        "created_at": room.created_at,
        "stage": stage,
        "items": _items(request.designs if request else None, level) if stage == "ready" else [],
        "status": _legacy(room.stages),
        "stages": [_row(r) for r in room.stages + (_live(request.stages) if request else ())],
    }
    if failure is not None:
        body["failure"] = failure
    if level is not None:
        body["confidence_level"] = level
    if request is not None:
        body["design_request_id"] = request.request_id
    if read:
        body["awaiting_brief"] = request is None
    return to_json_dict(RoomStatus.model_validate(body))


def _row(row: Stage) -> dict[str, Any]:
    out: dict[str, Any] = {"stage": row.stage, "status": row.status}
    if row.detail:
        out["detail"] = row.detail
    return out


def _legacy(rows: tuple[Stage, ...]) -> str:
    if any(r.status == "failed" for r in rows):
        return "failed"
    return "ready" if rows and all(r.status == "done" for r in rows) else "working"
