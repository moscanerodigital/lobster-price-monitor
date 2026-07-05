"""Gate Deploy CI fixture verification tests."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from refresh_ci_fixture_dates import refresh_bplus_fixtures
from test_verify_production_ci import _restore_project_data, _seed_project_data
from verify_deploy_gate import GateFailure

ROOT = Path(__file__).resolve().parent.parent


def _launchctl_output(*labels: str, serve_pid: int = 1234) -> str:
    lines = []
    for label in labels:
        if label.endswith(".serve"):
            lines.append(f"{serve_pid}\t0\t{label}")
        else:
            lines.append(f"-\t0\t{label}")
    return "\n".join(lines) + "\n"


def test_verify_deploy_gate_passes_with_bplus_fixtures() -> None:
    with tempfile.TemporaryDirectory() as td:
        data_dir = Path(td)
        refresh_bplus_fixtures(dst=data_dir)
        backup = _seed_project_data(data_dir)
        try:
            proc_board = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "board.py"), "--html"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
            assert proc_board.returncode == 0, proc_board.stderr

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify_deploy_gate.py"),
                    "--skip-scheduling",
                    "--skip-verify-suite",
                ],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
            )
        finally:
            _restore_project_data(backup)

    assert proc.returncode == 0, f"verify_deploy_gate failed:\n{proc.stdout}\n{proc.stderr}"
    assert "GATE DEPLOY VERIFICATION PASSED" in proc.stdout


@patch("verify_deploy_gate.subprocess.run")
@patch("verify_deploy_gate.sys.platform", "darwin")
def test_deploy_gate_passes_dry_run_scheduler(mock_run: MagicMock) -> None:
    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:2] == ["launchctl", "list"]:
            mock = MagicMock()
            mock.returncode = 0
            mock.stdout = _launchctl_output(
                "com.erik.lobster-price-monitor.scrape",
                "com.erik.lobster-price-monitor.serve",
                serve_pid=4321,
            )
            return mock
        return MagicMock(returncode=0, stdout="", stderr="")

    mock_run.side_effect = side_effect
    import verify_deploy_gate

    verify_deploy_gate.check_dry_run_scheduler_loaded()
    verify_deploy_gate.check_serve_running()


@patch("verify_deploy_gate.subprocess.run")
@patch("verify_deploy_gate.sys.platform", "darwin")
def test_deploy_gate_fails_when_ops_loaded(mock_run: MagicMock) -> None:
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=_launchctl_output(
            "com.erik.lobster-price-monitor.scrape",
            "com.erik.lobster-price-monitor.scrape.ops",
            "com.erik.lobster-price-monitor.serve",
        ),
    )
    import verify_deploy_gate

    try:
        verify_deploy_gate.check_dry_run_scheduler_loaded()
        raise AssertionError("expected GateFailure")
    except GateFailure as e:
        assert "ops" in str(e).lower()


@patch("verify_deploy_gate.subprocess.run")
@patch("verify_deploy_gate.sys.platform", "linux")
def test_deploy_gate_passes_linux_dry_run_timer(mock_run: MagicMock) -> None:
    def side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
        if cmd[:3] == ["systemctl", "is-enabled", "lobster-price-monitor-scrape.timer"]:
            return MagicMock(returncode=0, stdout="enabled\n")
        if cmd[:3] == ["systemctl", "is-enabled", "lobster-price-monitor-scrape.ops.timer"]:
            return MagicMock(returncode=1, stdout="disabled\n")
        if cmd[:3] == ["systemctl", "is-active", "lobster-price-monitor-serve"]:
            return MagicMock(returncode=0, stdout="active\n")
        return MagicMock(returncode=0, stdout="")

    mock_run.side_effect = side_effect
    import verify_deploy_gate

    verify_deploy_gate.check_dry_run_scheduler_loaded()
    verify_deploy_gate.check_serve_running()


def main() -> int:
    tests = [
        test_verify_deploy_gate_passes_with_bplus_fixtures,
        test_deploy_gate_passes_dry_run_scheduler,
        test_deploy_gate_fails_when_ops_loaded,
        test_deploy_gate_passes_linux_dry_run_timer,
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
    print("\nAll Gate Deploy CI tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
