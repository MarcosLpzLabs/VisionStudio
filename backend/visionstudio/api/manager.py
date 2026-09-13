"""Gestor de conexiones WebSocket.

Permite difundir mensajes a todos los clientes conectados. El `broadcast` es
SÍNCRONO (lo llama el hilo del RunLoop) y programa el envío asíncrono en el
bucle de eventos de FastAPI:

- Si se llama desde el hilo del bucle -> `create_task`.
- Si se llama desde otro hilo (RunLoop) -> `run_coroutine_threadsafe`.

Los clientes que fallan al recibir se desconectan sin afectar al resto.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional, Set


class WSManager:
    """Conjunto de conexiones WebSocket activas."""

    def __init__(self) -> None:
        self._connections: Set[Any] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Registra el bucle de eventos de FastAPI (al conectar el primer WS)."""
        self._loop = loop

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._connections)

    async def connect(self, websocket: Any) -> None:
        with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: Any) -> None:
        with self._lock:
            self._connections.discard(websocket)

    def broadcast(self, message: dict) -> None:
        """Programa el envío del mensaje a todos los clientes (no bloquea)."""
        if not self._connections:
            return  # sin clientes: nada que hacer
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        try:
            # ¿Estamos en el hilo del bucle de eventos?
            asyncio.get_running_loop()
            loop.create_task(self._broadcast_all(message))
        except RuntimeError:
            # Otro hilo (RunLoop): programar de forma segura en el bucle.
            asyncio.run_coroutine_threadsafe(self._broadcast_all(message), loop)

    async def _broadcast_all(self, message: dict) -> None:
        # Copia de la lista para no iterar un conjunto que puede cambiar.
        with self._lock:
            targets = list(self._connections)
        broken = []
        for websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                broken.append(websocket)
        for websocket in broken:
            await self.disconnect(websocket)