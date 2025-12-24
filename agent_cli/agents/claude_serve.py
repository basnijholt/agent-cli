"""Claude Code remote server command for Agent CLI."""

from __future__ import annotations

import ipaddress
import json
from datetime import UTC
from importlib.util import find_spec
from pathlib import Path

import typer

from agent_cli import opts
from agent_cli.cli import app
from agent_cli.core.utils import (
    console,
    print_command_line_args,
    print_error_message,
)

has_uvicorn = find_spec("uvicorn") is not None
has_fastapi = find_spec("fastapi") is not None
has_claude_sdk = find_spec("claude_agent_sdk") is not None

# Default paths for SSL certificates
SSL_CERT_DIR = Path.home() / ".config" / "agent-cli" / "ssl"
SSL_CERT_FILE = SSL_CERT_DIR / "cert.pem"
SSL_KEY_FILE = SSL_CERT_DIR / "key.pem"


def _generate_self_signed_cert() -> tuple[Path, Path]:
    """Generate a self-signed SSL certificate for HTTPS."""
    from datetime import datetime, timedelta  # noqa: PLC0415

    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: PLC0415
    from cryptography.x509.oid import NameOID  # noqa: PLC0415

    SSL_CERT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate private key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Generate certificate
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "Claude Code Server"),
        ],
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                ],
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Write certificate and key
    SSL_KEY_FILE.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    SSL_CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    return SSL_CERT_FILE, SSL_KEY_FILE


def run_claude_server(
    host: str = "0.0.0.0",  # noqa: S104
    port: int = 8765,
    reload: bool = False,
    cwd: Path | None = None,
    projects: dict[str, str] | None = None,
    default_project: str | None = None,
    ssl: bool = False,
) -> None:
    """Run the Claude Code FastAPI server."""
    import os  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    # Set working directory for the API to use
    if cwd:
        os.environ["CLAUDE_API_CWD"] = str(cwd.resolve())

    # Pass projects config via environment variable
    if projects:
        os.environ["CLAUDE_API_PROJECTS"] = json.dumps(projects)
    if default_project:
        os.environ["CLAUDE_API_DEFAULT_PROJECT"] = default_project

    ssl_keyfile = None
    ssl_certfile = None
    if ssl:
        if not SSL_CERT_FILE.exists() or not SSL_KEY_FILE.exists():
            console.print("[yellow]Generating self-signed SSL certificate...[/yellow]")
            _generate_self_signed_cert()
        ssl_certfile = str(SSL_CERT_FILE)
        ssl_keyfile = str(SSL_KEY_FILE)

    uvicorn.run(
        "agent_cli.claude_api:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )


@app.command("claude-serve")
def claude_serve(
    host: str = typer.Option(
        "0.0.0.0",  # noqa: S104
        help="Host to bind the server to",
    ),
    port: int = typer.Option(8880, help="Port to bind the server to"),
    cwd: Path = typer.Option(  # noqa: B008
        None,
        help="Working directory for Claude Code (defaults to current directory)",
    ),
    reload: bool = typer.Option(
        False,  # noqa: FBT003
        "--reload",
        help="Enable auto-reload for development",
    ),
    ssl: bool = typer.Option(
        False,  # noqa: FBT003
        "--ssl",
        help="Enable HTTPS with self-signed certificate (required for voice on Safari/iOS)",
    ),
    config_file: str | None = opts.CONFIG_FILE,
    print_args: bool = opts.PRINT_ARGS,
) -> None:
    """Start Claude Code remote server for iOS/web access.

    This starts a FastAPI server that exposes Claude Code capabilities via REST and WebSocket
    endpoints, allowing remote access from iOS Shortcuts, web interfaces, or any HTTP client.

    Prerequisites:
    - Run `claude /login` once to authenticate with your Claude.ai account
    - Install dependencies: pip install agent-cli[claude]

    Example usage:
        agent-cli claude-serve --port 8765

    Configure projects in config.toml:
        [claude_server]
        default_project = "my-project"

        [claude_server.projects]
        my-project = "/path/to/project"
        dotfiles = "~/.dotfiles"

    Endpoints:
    - POST /prompt - Simple prompt with auto project management
    - GET /logs - View recent logs
    - GET /log/{id} - View log details
    - GET /projects - List configured projects
    - POST /switch-project - Switch current project
    """
    if print_args:
        print_command_line_args(locals())

    if not has_uvicorn or not has_fastapi:
        msg = (
            "uvicorn or fastapi is not installed. "
            "Please install with: pip install agent-cli[claude]"
        )
        print_error_message(msg)
        raise typer.Exit(1)

    if not has_claude_sdk:
        msg = (
            "claude-agent-sdk is not installed. Please install with: pip install agent-cli[claude]"
        )
        print_error_message(msg)
        raise typer.Exit(1)

    # Load config for projects
    from agent_cli.config import load_config  # noqa: PLC0415

    config = load_config(config_file)
    claude_server_config = config.get("claude_server", {})
    projects = claude_server_config.get("projects", {})
    default_project = claude_server_config.get("default_project")

    # Default to current directory if not specified
    if cwd is None:
        cwd = Path.cwd()

    # If no projects configured, add cwd as default project
    if not projects:
        projects = {"default": str(cwd.resolve())}
        default_project = "default"

    protocol = "https" if ssl else "http"
    console.print(
        f"[bold green]Starting Claude Code remote server on {protocol}://{host}:{port}[/bold green]",
    )
    console.print(f"[dim]Working directory: {cwd.resolve()}[/dim]")
    if projects:
        console.print(f"[dim]Projects: {', '.join(projects.keys())}[/dim]")
        if default_project:
            console.print(f"[dim]Default project: {default_project}[/dim]")
    console.print()
    console.print("[bold]Endpoints:[/bold]")
    console.print(f"  Chat {protocol}://{host}:{port}/chat")
    console.print(f"  POST {protocol}://{host}:{port}/prompt")
    console.print(f"  GET  {protocol}://{host}:{port}/logs")
    console.print()

    if ssl:
        console.print(
            "[yellow]HTTPS enabled (self-signed cert) - accept certificate warning in browser[/yellow]",
        )
    if reload:
        console.print("[yellow]Auto-reload enabled for development[/yellow]")

    run_claude_server(
        host=host,
        port=port,
        reload=reload,
        cwd=cwd,
        projects=projects,
        default_project=default_project,
        ssl=ssl,
    )
