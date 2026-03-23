from __future__ import annotations

from datetime import datetime, timezone

from control_okua.core.control_plane.audit import (
    ControlAuditEventType,
    build_control_audit_event,
)


def test_build_control_audit_event_contains_required_fields() -> None:
    fixed_now = datetime(2026, 3, 23, 12, 0, 0, 123000, tzinfo=timezone.utc)
    event = build_control_audit_event(
        event_type=ControlAuditEventType.COMMAND_SENT,
        command_name="PING",
        cmd_id=0x01,
        node_ip="192.168.0.10",
        node_id=12,
        cmd_seq=100,
        nonce=0x1234000000000001,
        attempt_index=1,
        utc_now_provider=lambda: fixed_now,
    )
    payload = event.to_dict()

    assert payload["ts_utc"] == "2026-03-23T12:00:00.123Z"
    assert payload["event_type"] == "command_sent"
    assert payload["command_name"] == "PING"
    assert payload["cmd_id"] == 0x01
    assert payload["node_ip"] == "192.168.0.10"
    assert payload["node_id"] == 12
    assert payload["cmd_seq"] == 100
    assert payload["nonce"] == 0x1234000000000001
    assert payload["attempt_index"] == 1


def test_build_control_audit_event_keeps_ack_fields_when_present() -> None:
    fixed_now = datetime(2026, 3, 23, 12, 1, 2, 456000, tzinfo=timezone.utc)
    event = build_control_audit_event(
        event_type=ControlAuditEventType.COMMAND_ACK,
        command_name="REQUEST_STAT_NOW",
        cmd_id=0x07,
        node_ip="10.0.0.77",
        node_id=33,
        cmd_seq=200,
        nonce=0xABCDEF0102030405,
        attempt_index=2,
        ack_stage=1,
        status_code=0,
        err_detail=0,
        detail="ack matched",
        utc_now_provider=lambda: fixed_now,
    )

    assert event.ts_utc == "2026-03-23T12:01:02.456Z"
    assert event.event_type == "command_ack"
    assert event.ack_stage == 1
    assert event.status_code == 0
    assert event.err_detail == 0
    assert event.detail == "ack matched"
