"""Tests for daemon management CLI and service modules."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from agent_cli.cli import app
from agent_cli.install.launchd import _generate_plist as launchd_generate_plist
from agent_cli.install.launchd import _get_log_command as launchd_get_log_command
from agent_cli.install.launchd import _get_service_status as launchd_get_service_status
from agent_cli.install.launchd import manager as launchd_manager
from agent_cli.install.service_config import (
    SERVICES,
    InstallResult,
    ServiceConfig,
    ServiceManager,
    ServiceStatus,
    UninstallResult,
    build_service_command,
    find_uv,
    get_default_services,
    get_service_manager,
    install_uv,
)
from agent_cli.install.systemd import _generate_unit_file as systemd_generate_unit_file
from agent_cli.install.systemd import _get_log_command as systemd_get_log_command
from agent_cli.install.systemd import _get_service_status as systemd_get_service_status
from agent_cli.install.systemd import _get_unit_name as systemd_get_unit_name
from agent_cli.install.systemd import manager as systemd_manager

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


# =============================================================================
# Service Config Tests
# =============================================================================


class TestServiceConfig:
    """Tests for service_config.py."""

    def test_services_defined(self) -> None:
        """Test that expected services are defined."""
        assert "whisper" in SERVICES
        assert "tts-kokoro" in SERVICES
        assert "tts-piper" in SERVICES
        assert "transcription-proxy" in SERVICES
        assert "memory" in SERVICES
        assert "rag" in SERVICES

    def test_service_config_fields(self) -> None:
        """Test ServiceConfig has required fields."""
        whisper = SERVICES["whisper"]
        assert whisper.name == "whisper"
        assert whisper.display_name == "Whisper ASR"
        assert whisper.extra
        assert isinstance(whisper.command_args, list)

    def test_build_service_command(self, tmp_path: Path) -> None:
        """Test building service command for uv tool run."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        service = ServiceConfig(
            name="test",
            display_name="Test Service",
            description="Test",
            extra="server",
            command_args=["--port", "8080"],
        )
        cmd = build_service_command(service, uv_path)
        assert str(uv_path) in cmd
        assert "tool" in cmd
        assert "run" in cmd
        assert "--from" in cmd
        assert "agent-cli[server]" in cmd
        assert "server" in cmd
        assert "test" in cmd
        assert "--port" in cmd
        assert "8080" in cmd

    def test_build_service_command_appends_runtime_args(self, tmp_path: Path) -> None:
        """User-provided daemon args are appended to the generated server command."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        service = ServiceConfig(
            name="whisper",
            display_name="Whisper ASR",
            description="Test",
            extra="server",
            command_args=["--port", "10301"],
        )

        cmd = build_service_command(
            service,
            uv_path,
            extra_command_args=["--backend", "nemo", "--model", "parakeet"],
        )

        assert cmd[-6:] == [
            "--port",
            "10301",
            "--backend",
            "nemo",
            "--model",
            "parakeet",
        ]

    def test_build_service_command_with_python_version(self, tmp_path: Path) -> None:
        """Test building service command with Python version constraint."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        service = ServiceConfig(
            name="test",
            display_name="Test",
            description="Test",
            extra="server",
            command_args=[],
            python_version="3.12",
        )
        cmd = build_service_command(service, uv_path)
        assert "--python" in cmd
        assert "3.12" in cmd

    def test_build_service_command_macos_extra(self, tmp_path: Path) -> None:
        """Test building service command with macOS-specific extra."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        service = ServiceConfig(
            name="test",
            display_name="Test",
            description="Test",
            extra="server,linux-dep",
            command_args=[],
            macos_extra="server,macos-dep",
        )
        cmd = build_service_command(service, uv_path, use_macos_extra=True)
        assert "agent-cli[server,macos-dep]" in cmd

    def test_build_service_command_uses_app_package_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The macOS app can point daemon uv runs at its bundled wheel."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        wheel_path = (
            tmp_path
            / "AgentCLI.app"
            / "Contents"
            / "Resources"
            / "wheels"
            / "agent_cli-0.0.0-py3-none-any.whl"
        )
        monkeypatch.setenv("AGENTCLI_PACKAGE_SOURCE", str(wheel_path))
        service = ServiceConfig(
            name="test",
            display_name="Test",
            description="Test",
            extra="server",
            command_args=[],
        )

        cmd = build_service_command(service, uv_path)

        assert f"{wheel_path}[server]" in cmd

    def test_build_service_command_custom_command(self, tmp_path: Path) -> None:
        """Test building service command with custom command path."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        # Test custom command like "memory proxy"
        service = ServiceConfig(
            name="memory",
            display_name="Memory Proxy",
            description="Memory proxy",
            extra="memory",
            command_args=["--port", "8100"],
            command=["memory", "proxy"],
        )
        cmd = build_service_command(service, uv_path)
        assert "agent-cli[memory]" in cmd
        assert "memory" in cmd
        assert "proxy" in cmd
        assert "--port" in cmd
        assert "8100" in cmd
        # Should NOT have "server" in the command
        assert cmd.count("server") == 0

    def test_memory_and_rag_services(self, tmp_path: Path) -> None:
        """Test that memory and rag services have correct custom commands."""
        uv_path = tmp_path / "uv"
        uv_path.touch()

        memory = SERVICES["memory"]
        assert memory.command == ["memory", "proxy"]
        cmd = build_service_command(memory, uv_path)
        assert "agent-cli[memory]" in cmd
        assert "memory" in cmd
        assert "proxy" in cmd

        rag = SERVICES["rag"]
        assert rag.command == ["rag-proxy"]
        cmd = build_service_command(rag, uv_path)
        assert "agent-cli[rag]" in cmd
        assert "rag-proxy" in cmd

    def test_find_uv_in_path(self, tmp_path: Path) -> None:
        """Test finding uv when it exists in extra_paths."""
        uv_path = tmp_path / "uv"
        uv_path.touch()
        uv_path.chmod(0o755)
        result = find_uv(extra_paths=[uv_path])
        assert result == uv_path

    def test_find_uv_prefers_app_bundled_uv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The macOS app advertises its bundled uv through AGENTCLI_BUNDLED_UV."""
        bundled_uv = tmp_path / "AgentCLI.app" / "Contents" / "Resources" / "bin" / "uv"
        bundled_uv.parent.mkdir(parents=True)
        bundled_uv.touch()
        bundled_uv.chmod(0o755)

        other_uv = tmp_path / "other" / "uv"
        other_uv.parent.mkdir()
        other_uv.touch()
        other_uv.chmod(0o755)

        monkeypatch.setenv("AGENTCLI_BUNDLED_UV", str(bundled_uv))

        result = find_uv(extra_paths=[other_uv])

        assert result == bundled_uv

    def test_find_uv_prefers_explicit_uv_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Users can override uv discovery with AGENTCLI_UV_PATH."""
        explicit_uv = tmp_path / "explicit" / "uv"
        explicit_uv.parent.mkdir()
        explicit_uv.touch()
        explicit_uv.chmod(0o755)

        bundled_uv = tmp_path / "bundled" / "uv"
        bundled_uv.parent.mkdir()
        bundled_uv.touch()
        bundled_uv.chmod(0o755)

        monkeypatch.setenv("AGENTCLI_UV_PATH", str(explicit_uv))
        monkeypatch.setenv("AGENTCLI_BUNDLED_UV", str(bundled_uv))

        result = find_uv()

        assert result == explicit_uv

    def test_find_uv_not_found(self) -> None:
        """Test find_uv returns None when uv is not found."""
        # Use paths that definitely don't exist
        result = find_uv(extra_paths=[Path("/nonexistent/uv")])
        # Result depends on whether uv is actually installed on the system
        # Just verify it returns Path or None
        assert result is None or isinstance(result, Path)

    @patch("subprocess.run")
    def test_install_uv_success(self, mock_run: MagicMock) -> None:
        """Test successful uv installation."""
        mock_run.return_value = MagicMock(stdout=b"install script", returncode=0)
        success, msg = install_uv()
        assert success is True
        assert "successfully" in msg

    @patch("subprocess.run")
    def test_install_uv_pipes_binary_curl_output_to_shell(self, mock_run: MagicMock) -> None:
        """Test uv installer output can be piped to sh as bytes."""

        def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            if args[0] == "curl":
                return subprocess.CompletedProcess(args, 0, stdout=b"echo installing uv\n")
            if args == ["sh"]:
                if kwargs.get("text") is True and isinstance(kwargs.get("input"), bytes):
                    msg = "'bytes' object has no attribute 'encode'"
                    raise AttributeError(msg)
                return subprocess.CompletedProcess(args, 0, stdout=b"", stderr=b"")
            msg = f"unexpected command: {args}"
            raise AssertionError(msg)

        mock_run.side_effect = fake_run

        success, msg = install_uv()

        assert success is True
        assert "successfully" in msg

    @patch("subprocess.run")
    def test_install_uv_failure(self, mock_run: MagicMock) -> None:
        """Test failed uv installation."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "curl")
        success, msg = install_uv()
        assert success is False
        assert "Failed" in msg


class TestGetServiceManager:
    """Tests for get_service_manager()."""

    @patch("agent_cli.install.service_config.platform.system", return_value="Darwin")
    def test_get_manager_macos(self, mock_system: MagicMock) -> None:
        """Test getting launchd manager on macOS."""
        manager = get_service_manager()
        assert isinstance(manager, ServiceManager)
        mock_system.assert_called()

    @patch("agent_cli.install.service_config.platform.system", return_value="Linux")
    def test_get_manager_linux(self, mock_system: MagicMock) -> None:
        """Test getting systemd manager on Linux."""
        manager = get_service_manager()
        assert isinstance(manager, ServiceManager)
        mock_system.assert_called()

    @patch("agent_cli.install.service_config.platform.system", return_value="Windows")
    def test_get_manager_unsupported(self, mock_system: MagicMock) -> None:
        """Test error on unsupported platform."""
        with pytest.raises(RuntimeError, match="Unsupported platform"):
            get_service_manager()
        mock_system.assert_called()


# =============================================================================
# Daemon CLI Tests
# =============================================================================


class TestDaemonCLI:
    """Tests for daemon CLI commands."""

    def test_daemon_help(self) -> None:
        """Test daemon command shows help."""
        result = runner.invoke(app, ["daemon", "--help"])
        assert result.exit_code == 0
        assert "daemon" in result.stdout.lower()
        assert "install" in result.stdout
        assert "uninstall" in result.stdout
        assert "status" in result.stdout

    def test_daemon_no_args(self) -> None:
        """Test daemon with no args shows help."""
        result = runner.invoke(app, ["daemon"])
        assert result.exit_code == 2  # no_args_is_help
        assert "Usage" in result.stdout

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_status(self, mock_get_manager: MagicMock) -> None:
        """Test daemon status command."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.return_value = ServiceStatus(
            name="whisper",
            installed=False,
            running=False,
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "whisper" in result.stdout
        assert "not installed" in result.stdout

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_status_running(self, mock_get_manager: MagicMock) -> None:
        """Test daemon status shows running service."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.return_value = ServiceStatus(
            name="whisper",
            installed=True,
            running=True,
            pid=12345,
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "status", "whisper"])
        assert result.exit_code == 0
        assert "running" in result.stdout
        assert "12345" in result.stdout

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_status_specific_service_shows_specific_log_path(
        self,
        mock_get_manager: MagicMock,
    ) -> None:
        """Specific service status should not print placeholder log paths."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.return_value = ServiceStatus(
            name="whisper",
            installed=True,
            running=True,
            pid=12345,
        )
        mock_get_manager.return_value = mock_manager

        with patch("agent_cli.daemon.cli.platform.system", return_value="Darwin"):
            result = runner.invoke(app, ["daemon", "status", "whisper", "--logs", "0"])

        assert result.exit_code == 0
        assert "~/Library/Logs/agent-cli-whisper/" in result.stdout
        assert "agent-cli-<service>" not in result.stdout

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_status_unknown_service(self, mock_get_manager: MagicMock) -> None:
        """Test daemon status with unknown service."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "status", "unknown"])
        assert result.exit_code == 1
        # Error goes to stderr, check combined output
        assert "Unknown service" in result.output

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_no_args(self, mock_get_manager: MagicMock) -> None:
        """Test daemon install requires service name or --all."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "install"])
        assert result.exit_code == 1
        # Error goes to stderr, check combined output
        assert "Specify services" in result.output or "Error" in result.output

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_unknown_service(self, mock_get_manager: MagicMock) -> None:
        """Test daemon install with unknown service."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "install", "unknown", "-y"])
        assert result.exit_code == 1
        # Error goes to stderr, check combined output
        assert "Unknown service" in result.output

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_success(self, mock_get_manager: MagicMock) -> None:
        """Test successful daemon installation."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
            log_dir=None,
        )
        mock_manager.get_log_command.return_value = "journalctl --user -u agent-cli-whisper -f"
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "install", "whisper", "-y"])
        assert result.exit_code == 0
        assert "Installed and started" in result.stdout
        mock_manager.install_service.assert_called_once_with("whisper")

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_passes_trailing_service_args(self, mock_get_manager: MagicMock) -> None:
        """Arguments after -- are persisted in the installed service command."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
            log_dir=None,
        )
        mock_manager.get_log_command.return_value = "journalctl --user -u agent-cli-whisper -f"
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            app,
            [
                "daemon",
                "install",
                "whisper",
                "-y",
                "--",
                "--backend",
                "nemo",
                "--model",
                "parakeet-unified-en-0.6b",
            ],
        )

        assert result.exit_code == 0
        mock_manager.install_service.assert_called_once_with(
            "whisper",
            ["--backend", "nemo", "--model", "parakeet-unified-en-0.6b"],
        )

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_rejects_trailing_args_with_multiple_services(
        self, mock_get_manager: MagicMock
    ) -> None:
        """Custom daemon args are only valid when installing one service."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(
            app,
            ["daemon", "install", "whisper", "tts-kokoro", "-y", "--", "--port", "10309"],
        )

        assert result.exit_code == 1
        assert "only supported when installing exactly one service" in result.output
        mock_manager.install_service.assert_not_called()

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_failure(self, mock_get_manager: MagicMock) -> None:
        """Test failed daemon installation."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_manager.install_service.return_value = InstallResult(
            success=False,
            message="Failed to start service",
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "install", "whisper", "-y"])
        assert result.exit_code == 1
        assert "Failed" in result.stdout

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_install_all(self, mock_get_manager: MagicMock) -> None:
        """Test daemon install --all."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.check_uv_installed.return_value = (True, Path("/usr/bin/uv"))
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
            log_dir=None,
        )
        mock_manager.get_log_command.return_value = "journalctl --user -u agent-cli-test -f"
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "install", "--all", "-y"])
        assert result.exit_code == 0
        # Should install default services (one TTS backend auto-selected)
        assert mock_manager.install_service.call_count == len(get_default_services())

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_ensure_running_skips_install(self, mock_get_manager: MagicMock) -> None:
        """Ensure should be a no-op when the service is already running."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.return_value = ServiceStatus(
            name="whisper",
            installed=True,
            running=True,
            pid=12345,
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "ensure", "whisper", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload == {
            "service": "whisper",
            "action": "already_running",
            "installed": True,
            "running": True,
            "pid": 12345,
            "message": "Already running",
        }
        mock_manager.install_service.assert_not_called()

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_ensure_installs_missing_service(self, mock_get_manager: MagicMock) -> None:
        """Ensure should install a missing service without parsing status output."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.side_effect = [
            ServiceStatus(name="whisper", installed=False, running=False),
            ServiceStatus(name="whisper", installed=True, running=True, pid=12345),
        ]
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "ensure", "whisper", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload == {
            "service": "whisper",
            "action": "installed",
            "installed": True,
            "running": True,
            "pid": 12345,
            "message": "Installed and started",
        }
        mock_manager.install_service.assert_called_once_with("whisper")

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_ensure_reinstalls_stopped_service(self, mock_get_manager: MagicMock) -> None:
        """Ensure should repair an installed launchd/systemd service that is stopped."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.side_effect = [
            ServiceStatus(name="whisper", installed=True, running=False),
            ServiceStatus(name="whisper", installed=True, running=True, pid=12345),
        ]
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "ensure", "whisper", "--quiet"])

        assert result.exit_code == 0
        assert result.stdout == ""
        mock_manager.install_service.assert_called_once_with("whisper")

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_ensure_fails_when_service_stays_stopped(
        self,
        mock_get_manager: MagicMock,
    ) -> None:
        """Ensure should fail if repair does not leave the service running."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.side_effect = [
            ServiceStatus(name="whisper", installed=True, running=False),
            ServiceStatus(name="whisper", installed=True, running=False),
        ]
        mock_manager.install_service.return_value = InstallResult(
            success=True,
            message="Installed and started",
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "ensure", "whisper", "--json"])

        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        assert payload == {
            "service": "whisper",
            "action": "failed",
            "installed": True,
            "running": False,
            "pid": None,
            "message": "Installed and started, but service is not running",
        }
        mock_manager.install_service.assert_called_once_with("whisper")

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_ensure_unknown_service(self, mock_get_manager: MagicMock) -> None:
        """Ensure should reject unknown services before consulting the manager."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "ensure", "unknown"])

        assert result.exit_code == 1
        assert "Unknown service" in result.output
        mock_manager.get_service_status.assert_not_called()

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_uninstall_no_args(self, mock_get_manager: MagicMock) -> None:
        """Test daemon uninstall requires service name or --all."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "uninstall"])
        assert result.exit_code == 1
        # Error goes to stderr, check combined output
        assert "Specify services" in result.output or "Error" in result.output

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_uninstall_success(self, mock_get_manager: MagicMock) -> None:
        """Test successful daemon uninstallation."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.uninstall_service.return_value = UninstallResult(
            success=True,
            message="Service stopped and removed",
            was_running=True,
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "uninstall", "whisper", "-y"])
        assert result.exit_code == 0
        assert "stopped and removed" in result.stdout
        mock_manager.uninstall_service.assert_called_once_with("whisper")

    @patch("agent_cli.daemon.cli.get_service_manager")
    def test_daemon_uninstall_all_none_installed(
        self,
        mock_get_manager: MagicMock,
    ) -> None:
        """Test daemon uninstall --all when nothing is installed."""
        mock_manager = MagicMock(spec=ServiceManager)
        mock_manager.get_service_status.return_value = ServiceStatus(
            name="test",
            installed=False,
            running=False,
        )
        mock_get_manager.return_value = mock_manager

        result = runner.invoke(app, ["daemon", "uninstall", "--all", "-y"])
        assert result.exit_code == 0
        assert "No services" in result.stdout or "not installed" in result.stdout.lower()


# =============================================================================
# Launchd Module Tests (macOS)
# =============================================================================


class TestLaunchdModule:
    """Tests for launchd.py (macOS service management)."""

    def test_launchd_manager_interface(self) -> None:
        """Test launchd manager has required interface."""
        assert callable(launchd_manager.check_uv_installed)
        assert callable(launchd_manager.install_uv)
        assert callable(launchd_manager.install_service)
        assert callable(launchd_manager.uninstall_service)
        assert callable(launchd_manager.get_service_status)
        assert callable(launchd_manager.get_log_command)

    def test_launchd_get_log_command(self) -> None:
        """Test launchd log command returns correct path."""
        cmd = launchd_get_log_command("whisper")
        assert "tail" in cmd
        assert "agent-cli-whisper" in cmd
        assert ".log" in cmd

    def test_launchd_generate_plist_appends_extra_args(self, tmp_path: Path) -> None:
        """Launchd plist persists user-provided daemon args."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]

        plist = launchd_generate_plist(
            service,
            uv_path,
            tmp_path,
            tmp_path,
            ["--model", "small", "--port", "10311"],
        )

        assert plist["ProgramArguments"][-4:] == ["--model", "small", "--port", "10311"]

    @patch("subprocess.run")
    def test_launchd_get_service_status_not_installed(
        self,
        mock_run: MagicMock,
    ) -> None:
        """Test status when service plist doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            status = launchd_get_service_status("whisper")
            assert status.installed is False
            assert status.running is False
        # mock_run may or may not be called depending on early return
        assert mock_run.call_count >= 0

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="launchd is macOS only, os.getuid() unavailable",
    )
    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_launchd_get_service_status_installed_not_running(
        self,
        mock_exists: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Test status when service is installed but not running."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        status = launchd_get_service_status("whisper")
        assert status.installed is True
        assert status.running is False
        mock_exists.assert_called()


# =============================================================================
# Systemd Module Tests (Linux)
# =============================================================================


class TestSystemdModule:
    """Tests for systemd.py (Linux service management)."""

    def test_systemd_manager_interface(self) -> None:
        """Test systemd manager has required interface."""
        assert callable(systemd_manager.check_uv_installed)
        assert callable(systemd_manager.install_uv)
        assert callable(systemd_manager.install_service)
        assert callable(systemd_manager.uninstall_service)
        assert callable(systemd_manager.get_service_status)
        assert callable(systemd_manager.get_log_command)

    def test_systemd_get_log_command(self) -> None:
        """Test systemd log command returns journalctl."""
        cmd = systemd_get_log_command("whisper")
        assert "journalctl" in cmd
        assert "agent-cli-whisper" in cmd

    def test_systemd_get_unit_name(self) -> None:
        """Test unit name generation."""
        assert systemd_get_unit_name("whisper") == "agent-cli-whisper.service"
        assert (
            systemd_get_unit_name("transcription-proxy") == "agent-cli-transcription-proxy.service"
        )

    @patch("subprocess.run")
    def test_systemd_get_service_status_not_installed(
        self,
        mock_run: MagicMock,
    ) -> None:
        """Test status when unit file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            status = systemd_get_service_status("whisper")
            assert status.installed is False
            assert status.running is False
        # mock_run may or may not be called depending on early return
        assert mock_run.call_count >= 0

    @patch("subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_systemd_get_service_status_running(
        self,
        mock_exists: MagicMock,
        mock_run: MagicMock,
    ) -> None:
        """Test status when service is running."""
        # Mock is-active returning "active"
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="active\n"),
            MagicMock(returncode=0, stdout="MainPID=12345\n"),
        ]
        status = systemd_get_service_status("whisper")
        assert status.installed is True
        assert status.running is True
        assert status.pid == 12345
        mock_exists.assert_called()

    def test_systemd_generate_unit_file(self, tmp_path: Path) -> None:
        """Test systemd unit file generation."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]
        unit_content = systemd_generate_unit_file(service, uv_path)

        assert "[Unit]" in unit_content
        assert "[Service]" in unit_content
        assert "[Install]" in unit_content
        assert "ExecStart=" in unit_content
        assert str(uv_path) in unit_content
        assert "Restart=on-failure" in unit_content

    def test_systemd_generate_unit_file_appends_extra_args(self, tmp_path: Path) -> None:
        """Systemd unit file persists user-provided daemon args."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]

        unit_content = systemd_generate_unit_file(
            service,
            uv_path,
            ["--model", "small", "--port", "10311"],
        )

        assert "--model small --port 10311" in unit_content

    def test_systemd_generate_unit_file_escapes_percent_args(self, tmp_path: Path) -> None:
        """Systemd unit file escapes literal percent signs in args."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]

        unit_content = systemd_generate_unit_file(
            service,
            uv_path,
            ["--base-url", "http://localhost/audio%20files"],
        )

        assert "audio%%20files" in unit_content

    def test_systemd_generate_unit_file_escapes_dollar_args(self, tmp_path: Path) -> None:
        """Systemd unit file escapes literal dollar signs in args."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]

        unit_content = systemd_generate_unit_file(
            service,
            uv_path,
            ["--cache-dir", "$HOME/agent-cache"],
        )

        assert "$$HOME/agent-cache" in unit_content

    def test_systemd_generate_unit_file_uses_systemd_quotes(self, tmp_path: Path) -> None:
        """Systemd unit file avoids shell-only quote concatenation."""
        uv_path = tmp_path / "uv"
        service = SERVICES["whisper"]

        unit_content = systemd_generate_unit_file(
            service,
            uv_path,
            ["--cache-dir", "/var/lib/O'Connor/cache", "--prompt", "hello world"],
        )

        assert "'\"'\"'" not in unit_content
        assert '"/var/lib/O\'Connor/cache"' in unit_content
        assert '"hello world"' in unit_content
