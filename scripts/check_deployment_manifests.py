"""Dependency-free static validation for the deployment manifests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, fragments: tuple[str, ...]) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    missing = [fragment for fragment in fragments if fragment not in content]
    if missing:
        raise SystemExit(f"{path}: missing required values: {', '.join(missing)}")


def forbid(path: str, fragments: tuple[str, ...]) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    present = [fragment for fragment in fragments if fragment in content]
    if present:
        raise SystemExit(
            f"{path}: contains divergent static values: {', '.join(present)}"
        )


def main() -> int:
    require(
        "deploy/systemd/singular.service",
        (
            "User=@SERVICE_USER@",
            "Group=@SERVICE_GROUP@",
            "WorkingDirectory=@SINGULAR_HOME@",
            "EnvironmentFile=/etc/singular/singular.env",
            "orchestrate run",
            "Restart=on-failure",
            "RestartSec=",
            "KillSignal=SIGTERM",
        ),
    )
    forbid(
        "deploy/systemd/singular.service",
        ("SINGULAR_ROOT=/var/lib/singular", "/opt/singular", "StateDirectory=singular"),
    )
    require(
        "Dockerfile",
        (
            "USER singular:singular",
            "STOPSIGNAL SIGTERM",
            "HEALTHCHECK",
            '"singular", "orchestrate", "run"',
        ),
    )
    require(
        "compose.yaml",
        (
            "restart: unless-stopped",
            "singular-mem:/var/lib/singular/mem",
            "singular-runs:/var/lib/singular/runs",
            "singular-config:/etc/singular",
            "healthcheck:",
            "limits:",
        ),
    )
    print("deployment manifests: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
