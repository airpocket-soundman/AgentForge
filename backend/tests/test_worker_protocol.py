"""MCP-like inter-worker protocol schema tests (pure, no Firestore)."""
from app.control_plane.worker_bus import validate_report, validate_request
from app.models.worker_protocol import WorkerReport, WorkerRequest


def test_valid_request_parses_with_from_alias():
    req, err = validate_request({
        "task_id": "t1", "message_id": "m1", "from": "Orchestrator#1",
        "to": "Reviewer", "intent": "review", "payload": {"feature": "counter"},
    })
    assert err is None and req is not None
    assert req.sender == "Orchestrator#1" and req.intent == "review"
    # round-trips back out under the 'from' alias
    assert req.model_dump(by_alias=True)["from"] == "Orchestrator#1"


def test_request_rejected_on_bad_intent():
    req, err = validate_request({
        "task_id": "t1", "message_id": "m1", "from": "A", "to": "B", "intent": "destroy",
    })
    assert req is None and err and "schema validation failed" in err


def test_request_rejected_on_missing_fields():
    req, err = validate_request({"intent": "plan"})
    assert req is None and err


def test_valid_report_correlates_via_in_reply_to():
    rep, err = validate_report({
        "task_id": "t1", "in_reply_to": "m1", "from": "Reviewer", "to": "Orchestrator#1",
        "status": "needs_revision", "findings": ["theme が規定外"],
    })
    assert err is None and rep is not None
    assert rep.in_reply_to == "m1" and rep.status == "needs_revision"
    assert rep.findings == ["theme が規定外"]


def test_report_rejected_on_bad_status():
    rep, err = validate_report({
        "task_id": "t1", "in_reply_to": "m1", "from": "R", "to": "O", "status": "maybe",
    })
    assert rep is None and err
