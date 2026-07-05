"""CI-safe scheduling gate tests (mock launchctl/systemctl)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import verify_ops_gate
import verify_production_gate
from verify_production_gate import GateFailure


def _launchctl_output(*labels: str, serve_pid: int = 1234) -> str:
    lines = []
    for label in labels:
        if label.endswith(".serve"):
            lines.append(f"{serve_pid}\t0\t{label}")
        else:
            lines.append(f"-\t0\t{label}")
    return "\n".join(lines) + "\n"


def _run_mock(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


@patch("verify_production_gate.subprocess.run")
@patch("verify_production_gate.sys.platform", "darwin")
def test_production_gate_passes_dry_run_scheduler(mock_run: MagicMock) -> None:
    mock_run.return_value = _run_mock(
        stdout=_launchctl_output(
            "com.erik.lobster-price-monitor.scrape",
            "com.erik.lobster-price-monitor.serve",
        )
    )
    verify_production_gate.check_scheduling()


@patch("verify_production_gate.subprocess.run")
@patch("verify_production_gate.sys.platform", "darwin")
def test_production_gate_passes_ops_scheduler(mock_run: MagicMock) -> None:
    mock_run.return_value = _run_mock(
        stdout=_launchctl_output(
            "com.erik.lobster-price-monitor.scrape.ops",
            "com.erik.lobster-price-monitor.serve",
        )
    )
    verify_production_gate.check_scheduling()


@patch("verify_production_gate.subprocess.run")
@patch("verify_production_gate.sys.platform", "darwin")
def test_production_gate_fails_without_scrape_scheduler(mock_run: MagicMock) -> None:
    mock_run.return_value = _run_mock(
        stdout=_launchctl_output("com.erik.lobster-price-monitor.serve")
    )
    try:
        verify_production_gate.check_scheduling()
        raise AssertionError("expected GateFailure")
    except GateFailure as e:
        assert "scrape agent not loaded" in str(e)


@patch("verify_production_gate.subprocess.run")
@patch("verify_production_gate.sys.platform", "linux")
def test_production_gate_passes_linux_ops_timer(mock_run: MagicMock) -> None:
    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:3] == ["systemctl", "is-active", "lobster-price-monitor-serve"]:
            return _run_mock(stdout="active\n")
        if cmd[:3] == ["systemctl", "list-timers", "--all"]:
            return _run_mock(stdout="lobster-price-monitor-scrape.ops.timer loaded\n")
        return _run_mock()

    mock_run.side_effect = side_effect
    verify_production_gate.check_scheduling()


@patch("verify_ops_gate._ops_unit_has_alerts_flag", return_value=True)
@patch("verify_ops_gate.subprocess.run")
@patch("verify_ops_gate.sys.platform", "darwin")
def test_ops_gate_passes_ops_loaded_dry_unloaded(
    mock_run: MagicMock,
    _mock_alerts: MagicMock,
) -> None:
    mock_run.return_value = _run_mock(
        stdout=_launchctl_output("com.erik.lobster-price-monitor.scrape.ops")
    )
    verify_ops_gate.check_ops_scheduler_loaded(skip_alerts_check=False)


@patch("verify_ops_gate._ops_unit_has_alerts_flag", return_value=True)
@patch("verify_ops_gate.subprocess.run")
@patch("verify_ops_gate.sys.platform", "darwin")
def test_ops_gate_fails_dry_run_still_loaded(
    mock_run: MagicMock,
    _mock_alerts: MagicMock,
) -> None:
    mock_run.return_value = _run_mock(
        stdout=_launchctl_output(
            "com.erik.lobster-price-monitor.scrape",
            "com.erik.lobster-price-monitor.scrape.ops",
        )
    )
    try:
        verify_ops_gate.check_ops_scheduler_loaded(skip_alerts_check=False)
        raise AssertionError("expected GateFailure")
    except verify_ops_gate.GateFailure as e:
        assert "dry-run" in str(e).lower()


@patch("verify_ops_gate._ops_unit_has_alerts_flag", return_value=True)
@patch("verify_ops_gate.subprocess.run")
@patch("verify_ops_gate.sys.platform", "darwin")
def test_ops_gate_fails_ops_not_loaded(
    mock_run: MagicMock,
    _mock_alerts: MagicMock,
) -> None:
    mock_run.return_value = _run_mock(stdout=_launchctl_output())
    try:
        verify_ops_gate.check_ops_scheduler_loaded(skip_alerts_check=False)
        raise AssertionError("expected GateFailure")
    except verify_ops_gate.GateFailure as e:
        assert "ops launchd agent" in str(e)


@patch("verify_ops_gate._ops_unit_has_alerts_flag", return_value=True)
@patch("verify_ops_gate.subprocess.run")
@patch("verify_ops_gate.sys.platform", "linux")
def test_ops_gate_passes_linux_ops_timer_enabled(
    mock_run: MagicMock,
    _mock_alerts: MagicMock,
) -> None:
    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:3] == ["systemctl", "is-enabled", "lobster-price-monitor-scrape.ops.timer"]:
            return _run_mock(stdout="enabled\n")
        if cmd[:3] == ["systemctl", "is-enabled", "lobster-price-monitor-scrape.timer"]:
            return _run_mock(returncode=1, stdout="disabled\n")
        return _run_mock()

    mock_run.side_effect = side_effect
    verify_ops_gate.check_ops_scheduler_loaded(skip_alerts_check=False)


def main() -> int:
    tests = [
        test_production_gate_passes_dry_run_scheduler,
        test_production_gate_passes_ops_scheduler,
        test_production_gate_fails_without_scrape_scheduler,
        test_production_gate_passes_linux_ops_timer,
        test_ops_gate_passes_ops_loaded_dry_unloaded,
        test_ops_gate_fails_dry_run_still_loaded,
        test_ops_gate_fails_ops_not_loaded,
        test_ops_gate_passes_linux_ops_timer_enabled,
    ]
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"  ✓ {name}")
        except Exception as e:
            print(f"  ✗ {name}: {e}")
            failed += 1

    if failed:
        print(f"\n{failed} test(s) failed")
        return 1
    print("\nAll scheduling gate tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
