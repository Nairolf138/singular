#!/usr/bin/env python3
"""Exercise a published Singular CLI across separate processes.

Run with an installed wheel or sdist, from outside the source checkout.
The default dummy provider demonstrates persistence and context retrieval,
not natural-language understanding.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

FIRST_PROMPT = "Je prépare une scène lumineuse avec un phare bleu."
SECOND_PROMPT = "Que sais-tu de ma scène lumineuse ?"
MEMORY_MARKER = "phare bleu"


def _run(cli: str, root: Path, *args: str) -> str:
    env = os.environ.copy()
    env["SINGULAR_ROOT"] = str(root)
    env["LLM_PROVIDER_FALLBACK"] = "dummy"
    completed = subprocess.run(
        [cli, "--root", str(root), *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(
            f"singular {' '.join(args[:2])} failed ({completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout


def _episodes(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Unused demo root")
    parser.add_argument(
        "--singular", default=shutil.which("singular"), help="Installed singular CLI"
    )
    parser.add_argument(
        "--provider", default="dummy", help="dummy, ollama, openai, ..."
    )
    args = parser.parse_args()
    if not args.singular:
        parser.error("install Singular or pass --singular /path/to/venv/bin/singular")

    root = args.root.expanduser().resolve()
    if (root / "lives" / "registry.json").exists():
        parser.error(f"demo root already contains a registry: {root}")
    root.mkdir(parents=True, exist_ok=True)
    life_name = f"Lumen Demo {uuid4().hex[:8]}"

    _run(
        args.singular,
        root,
        "lives",
        "create",
        "--name",
        life_name,
        "--starter-profile",
        "assistant",
    )
    registry_path = root / "lives" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    slug = registry["active"]
    life_path = Path(registry["lives"][slug]["path"])
    episodic_path = life_path / "mem" / "episodic.jsonl"

    _run(args.singular, root, "status", "--format", "json")
    _run(
        args.singular,
        root,
        "talk",
        "--provider",
        args.provider,
        "--prompt",
        FIRST_PROMPT,
    )
    first_episodes = _episodes(episodic_path)
    if not any(
        row.get("role") == "user" and row.get("text") == FIRST_PROMPT
        for row in first_episodes
    ):
        raise RuntimeError("first user message was not persisted")

    # Each CLI call above and below starts a new process. Nothing is carried
    # between calls except the life registry and its on-disk memory.
    _run(
        args.singular,
        root,
        "talk",
        "--provider",
        args.provider,
        "--prompt",
        SECOND_PROMPT,
    )
    second_episodes = _episodes(episodic_path)
    if second_episodes[: len(first_episodes)] != first_episodes:
        raise RuntimeError("existing episode history changed after restart")
    assistants = [row for row in second_episodes if row.get("role") == "assistant"]
    if len(assistants) != 2:
        raise RuntimeError(f"expected two assistant episodes, got {len(assistants)}")
    recalled = assistants[-1].get("context", {}).get("recalled_memories", [])
    matching = [row for row in recalled if MEMORY_MARKER in str(row.get("excerpt", ""))]
    if not matching:
        raise RuntimeError("first user memory was not retrieved for second talk")
    if json.loads(registry_path.read_text(encoding="utf-8"))["active"] != slug:
        raise RuntimeError("active life changed between processes")

    real_model = assistants[-1].get("llm_real") is True
    if args.provider != "dummy" and not real_model:
        raise RuntimeError("requested real provider fell back to dummy")
    print(
        json.dumps(
            {
                "result": "passed",
                "active_life": slug,
                "life_path": str(life_path),
                "episodic_path": str(episodic_path),
                "separate_cli_processes": 4,
                "first_message_persisted": True,
                "retrieved_excerpt": matching[0]["excerpt"],
                "real_llm_response": real_model,
                "provider": assistants[-1].get("active_provider"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"Démo échouée : {exc}", file=sys.stderr)
        sys.exit(1)
