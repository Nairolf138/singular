from __future__ import annotations

# mypy: ignore-errors

import asyncio
import json
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from singular.schedulers.reevaluation import alerts_from_records


def create_app(
    runs_dir: Path | str | None = None, psyche_file: Path | str | None = None
) -> FastAPI:
    """Create the dashboard FastAPI application."""
    base_dir = Path(os.environ.get("SINGULAR_HOME", "."))
    runs_path = Path(runs_dir) if runs_dir is not None else base_dir / "runs"
    psyche_path = (
        Path(psyche_file)
        if psyche_file is not None
        else base_dir / "mem" / "psyche.json"
    )
    app = FastAPI()

    def _compute_ecosystem() -> dict:
        organisms: dict[str, dict[str, object]] = {}
        if runs_path.exists():
            for file in runs_path.iterdir():
                if not file.is_file() or file.suffix != ".jsonl":
                    continue
                for line in file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    event = record.get("event")
                    interaction = record.get("interaction")

                    if event == "interaction" and isinstance(
                        record.get("organism"), str
                    ):
                        name = str(record["organism"])
                        state = organisms.setdefault(name, {"status": "alive"})
                        if "energy" in record:
                            state["energy"] = record["energy"]
                        if "resources" in record:
                            state["resources"] = record["resources"]
                        if "score" in record:
                            state["score"] = record["score"]
                        if "alive" in record:
                            state["status"] = (
                                "alive" if bool(record["alive"]) else "extinct"
                            )
                        if interaction:
                            state["last_interaction"] = interaction
                    elif event == "death":
                        skill = str(record.get("skill", ""))
                        if ":" in skill:
                            name, _ = skill.split(":", 1)
                            state = organisms.setdefault(name, {})
                            state["status"] = "extinct"
                    elif event is None and isinstance(record.get("skill"), str):
                        skill = record["skill"]
                        if ":" in skill:
                            name, _ = skill.split(":", 1)
                            state = organisms.setdefault(name, {"status": "alive"})
                            state["score"] = record.get("score_new")

        alive = sum(1 for state in organisms.values() if state.get("status") != "extinct")
        total_energy = sum(
            float(state.get("energy", 0.0))
            for state in organisms.values()
            if isinstance(state.get("energy"), (int, float))
        )
        total_resources = sum(
            float(state.get("resources", 0.0))
            for state in organisms.values()
            if isinstance(state.get("resources"), (int, float))
        )
        return {
            "organisms": organisms,
            "summary": {
                "total_organisms": len(organisms),
                "alive_organisms": alive,
                "total_energy": total_energy,
                "total_resources": total_resources,
            },
        }

    @app.get("/logs")
    def read_logs() -> dict[str, str]:
        logs: dict[str, str] = {}
        if runs_path.exists():
            for file in runs_path.iterdir():
                if file.is_file():
                    logs[file.name] = file.read_text()
        return logs

    @app.get("/psyche")
    def read_psyche() -> dict:
        if not psyche_path.exists():
            raise HTTPException(status_code=404, detail="psyche.json not found")
        return json.loads(psyche_path.read_text())

    @app.get("/ecosystem")
    def read_ecosystem() -> dict:
        return _compute_ecosystem()

    @app.get("/alerts")
    def read_alerts() -> dict[str, object]:
        if not runs_path.exists():
            return {"run": None, "alerts": []}

        files = sorted(
            [
                path
                for path in runs_path.iterdir()
                if path.is_file() and path.suffix == ".jsonl"
            ],
            key=lambda path: path.stat().st_mtime,
        )
        if not files:
            return {"run": None, "alerts": []}

        latest = files[-1]
        records: list[dict[str, object]] = []
        for line in latest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                records.append(payload)
        return {"run": latest.stem, "alerts": alerts_from_records(records)}

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        last_psyche_mtime: float | None = None
        log_cache: dict[str, tuple[float, str]] = {}
        last_logs: dict[str, str] = {}
        try:
            while True:
                if psyche_path.exists():
                    mtime = psyche_path.stat().st_mtime
                    if mtime != last_psyche_mtime:
                        last_psyche_mtime = mtime
                        data = json.loads(psyche_path.read_text())
                        await ws.send_json({"type": "psyche", "data": data})
                logs: dict[str, str] = {}
                if runs_path.exists():
                    current_files: set[str] = set()
                    for file in runs_path.iterdir():
                        if file.is_file():
                            current_files.add(file.name)
                            mtime = file.stat().st_mtime
                            cached = log_cache.get(file.name)
                            if not cached or cached[0] != mtime:
                                content = await asyncio.to_thread(file.read_text)
                                log_cache[file.name] = (mtime, content)
                            logs[file.name] = log_cache[file.name][1]
                    # Remove cache entries for files that no longer exist
                    for name in set(log_cache) - current_files:
                        del log_cache[name]
                else:
                    if log_cache:
                        log_cache.clear()
                if logs != last_logs:
                    last_logs = dict(logs)
                    await ws.send_json({"type": "logs", "data": logs})
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<html><head><title>Singular Dashboard</title></head><body>"
            "<h1>Singular Dashboard</h1>"
            "<h2>Psyche</h2><pre id='psyche'></pre>"
            "<h2>Ecosystem Summary</h2><pre id='ecosystem-summary'></pre>"
            "<h2>Organisms</h2><pre id='organisms'></pre>"
            "<h2>Runs</h2><div id='logs'></div>"
            "<script>const ws=new WebSocket(`ws://${location.host}/ws`);"
            "const loadEco=()=>fetch('/ecosystem').then(r=>r.json()).then(d=>{document.getElementById('ecosystem-summary').textContent=JSON.stringify(d.summary,null,2);document.getElementById('organisms').textContent=JSON.stringify(d.organisms,null,2);});"
            "loadEco();setInterval(loadEco,500);"
            "ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);}else if(m.type==='logs'){const d=document.getElementById('logs');d.innerHTML='';for(const [n,c] of Object.entries(m.data)){const pre=document.createElement('pre');pre.textContent=n+'\n'+c;d.appendChild(pre);}}};"
            "</script></body></html>"
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the dashboard using Uvicorn."""
    try:
        import uvicorn
    except ImportError as exc:
        print(
            "Uvicorn is required to run the dashboard. Install it with 'pip install uvicorn'.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc

    app = create_app()
    uvicorn.run(app, host=host, port=port)
