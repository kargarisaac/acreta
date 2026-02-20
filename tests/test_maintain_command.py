"""CLI maintain-command behavior tests."""

from __future__ import annotations

from acreta.app import daemon
from tests.helpers import run_cli_json


def test_maintain_dry_run_default_steps() -> None:
    code, payload = run_cli_json(["maintain", "--dry-run", "--json"])
    assert code == 0
    assert payload["partial"] is False
    assert payload["steps_requested"] == daemon.maintain_default_steps()


def test_maintain_step_order_filter() -> None:
    code, payload = run_cli_json(["maintain", "--dry-run", "--steps", "vectors,report,decay", "--json"])
    assert code == 0
    expected = [step for step in daemon.maintain_default_steps() if step in {"decay", "vectors", "report"}]
    assert payload["steps_requested"] == expected
