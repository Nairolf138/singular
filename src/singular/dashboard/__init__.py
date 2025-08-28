from __future__ import annotations

# mypy: ignore-errors

import asyncio
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse


def create_app(
    runs_dir: Path | str = Path("runs"), psyche_file: Path | str = Path("psyche.json")
) -> FastAPI:
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

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        last_psyche_mtime: float | None = None
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
                    for file in runs_path.iterdir():
                        if file.is_file():
                            logs[file.name] = file.read_text()
                if logs != last_logs:
                    last_logs = logs
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
            "<h2>Runs</h2><div id='logs'></div>"
            "<script>const ws=new WebSocket(`ws://${location.host}/ws`);"
            "ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.type==='psyche'){document.getElementById('psyche').textContent=JSON.stringify(m.data,null,2);}else if(m.type==='logs'){const d=document.getElementById('logs');d.innerHTML='';for(const [n,c] of Object.entries(m.data)){const pre=document.createElement('pre');pre.textContent=n+'\n'+c;d.appendChild(pre);}}};"
            "</script></body></html>"
        )

    return app


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Launch the dashboard using Uvicorn."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)
