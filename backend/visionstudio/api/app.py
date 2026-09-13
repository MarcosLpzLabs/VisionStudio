"""Aplicación FastAPI de VisionStudio.

Expone la API REST y el WebSocket de tiempo real. El controlador
(`AppController`) mantiene el estado; esta capa solo traduce HTTP/WS a sus
métodos. No contiene lógica de visión artificial.

Endpoints REST (docs/ARQUITECTURA.md §6):
- GET  /api/health            -> salud del servicio
- GET  /api/cameras           -> cámaras detectadas
- GET  /api/blocks            -> catálogo de bloques por categoría
- GET  /api/project           -> proyecto actual (JSON v1)
- PUT  /api/project           -> cargar proyecto
- GET  /api/state             -> estado del flujo
- GET  /api/results           -> últimos resultados serializables de los sinks
- POST /api/run/start|stop|pause|resume|step -> control de ejecución
- WS   /ws                    -> tiempo real (frames, estado, errores)
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from visionstudio import __version__
from visionstudio.api.controller import AppController
from visionstudio.api.manager import WSManager
from visionstudio.errors import EngineError, ErrorCode

# Instancia única de estado y de difusión.
controller = AppController()
manager = WSManager()
controller.set_broadcaster(manager.broadcast)

app = FastAPI(title="VisionStudio API", version=__version__)


# ===========================================================================
# Manejo de errores
# ===========================================================================
@app.exception_handler(EngineError)
async def engine_error_handler(request, exc: EngineError) -> JSONResponse:
    """Traduce un EngineError a HTTP 400 con código y parámetros estables."""
    return JSONResponse(status_code=400, content=exc.to_dict())


# ===========================================================================
# Modelos de petición
# ===========================================================================
class RunRequest(BaseModel):
    """Parámetros opcionales para arrancar el flujo."""

    mode: Optional[str] = None  # continuous | timer | manual
    interval_ms: Optional[int] = None


# ===========================================================================
# REST
# ===========================================================================
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/cameras")
async def cameras() -> dict:
    return {"cameras": controller.list_cameras()}


@app.get("/api/blocks")
async def blocks() -> dict:
    return {"categories": controller.block_catalog()}


@app.get("/api/project")
async def get_project() -> dict:
    return controller.get_project()


@app.put("/api/project")
async def put_project(project: dict) -> dict:
    # EngineError (proyecto inválido / en ejecución) lo maneja el handler global.
    controller.load_project(project)
    return {"ok": True}


@app.get("/api/state")
async def get_state() -> dict:
    return {"state": controller.state.value}


@app.get("/api/results")
async def get_results() -> dict:
    return {"results": controller.results()}


@app.post("/api/run/start")
async def run_start(payload: Optional[RunRequest] = None) -> dict:
    mode = payload.mode if payload else None
    interval_ms = payload.interval_ms if payload else None
    controller.start(mode=mode, interval_ms=interval_ms)
    return {"state": controller.state.value}


@app.post("/api/run/stop")
async def run_stop() -> dict:
    controller.stop()
    return {"state": controller.state.value}


@app.post("/api/run/pause")
async def run_pause() -> dict:
    controller.pause()
    return {"state": controller.state.value}


@app.post("/api/run/resume")
async def run_resume() -> dict:
    controller.resume()
    return {"state": controller.state.value}


@app.post("/api/run/step")
async def run_step() -> dict:
    controller.step()
    return {"state": controller.state.value}


# ===========================================================================
# WebSocket
# ===========================================================================
async def _handle_ws_command(message: dict) -> None:
    """Ejecuta un comando de control recibido por WebSocket."""
    command = message.get("command")
    if command == "start":
        controller.start(mode=message.get("mode"), interval_ms=message.get("interval_ms"))
    elif command == "stop":
        controller.stop()
    elif command == "pause":
        controller.pause()
    elif command == "resume":
        controller.resume()
    elif command == "step":
        controller.step()
    else:
        raise EngineError(ErrorCode.COMMAND_UNKNOWN, {"command": command})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    manager.set_loop(asyncio.get_running_loop())
    await manager.connect(websocket)
    # Estado inicial para que el cliente se sincronice al conectar.
    try:
        await websocket.send_json({"type": "state", "state": controller.state.value})
        while True:
            message = await websocket.receive_json()
            try:
                await _handle_ws_command(message)
            except EngineError as exc:
                await websocket.send_json({"type": "error", "code": exc.code, "params": exc.params})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)


# ===========================================================================
# Frontend compilado (fase 7). Se sirve si existe frontend/dist.
# ===========================================================================
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> dict:
        # Sin frontend compilado: la raíz informa de la API.
        return {"name": "VisionStudio API", "version": __version__, "docs": "/docs"}