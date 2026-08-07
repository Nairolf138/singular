"""Dependency-free static validation for the deployment manifests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, fragments: tuple[str, ...]) -> None:
    content = (ROOT / path).read_text(encoding="utf-8")
    missing = [fragment for fragment in fragments if fragment not in content]
    if missing:
        raise SystemExit(f"{path}: missing required values: {', '.join(missing)}")


def main() -> int:
    require(
        "deploy/systemd/singular.service",
        (
            "User=singular",
            "WorkingDirectory=",
            "singular orchestrate run",
            "Restart=on-failure",
            "RestartSec=",
            "StateDirectory=singular",
            "KillSignal=SIGTERM",
        ),
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
