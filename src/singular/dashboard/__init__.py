from __future__ import annotations

import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse


def create_app(runs_dir: Path | str = Path("runs"), psyche_file: Path | str = Path("psyche.json")) -> FastAPI:
    """Create the dashboard FastAPI application."""
    runs_path = Path(runs_dir)
    psyche_path = Path(psyche_file)
    app = FastAPI()

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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (
            "<html><head><title>Singular Dashboard</title></head><body>"
            "<h1>Singular Dashboard</h1>"
            "<h2>Psyche</h2><pre id='psyche'></pre>"
            "<h2>Runs</h2><div id='logs'></div>"
            "<script>async function load(){"
            "const ps=await fetch('/psyche').then(r=>r.json()).catch(()=>null);"
            "document.getElementById('psyche').textContent=JSON.stringify(ps,null,2);"
            "const ls=await fetch('/logs').then(r=>r.json());"
            "const div=document.getElementById('logs');"
            "for(const [n,c] of Object.entries(ls)){const pre=document.createElement('pre');pre.textContent=n+'\n'+c;div.appendChild(pre);}"
            "}load();</script></body></html>"
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the dashboard using Uvicorn."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)
