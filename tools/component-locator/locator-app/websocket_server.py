import asyncio
import json
import threading

import websockets


class WsServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 9876):
        self.host = host
        self.port = port
        self._thread: threading.Thread | None = None
        self._stop: asyncio.Event | None = None
        self._clients: set[websockets.WebSocketServerProtocol] = set()
        self.on_element = None

    async def _handler(self, ws: websockets.WebSocketServerProtocol):
        self._clients.add(ws)
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "ELEMENT_COLLECTED" and self.on_element:
                    self.on_element(msg.get("data", {}))
        finally:
            self._clients.discard(ws)

    async def _run(self):
        self._stop = asyncio.Event()
        async with websockets.serve(self._handler, self.host, self.port):
            await self._stop.wait()

    def start(self):
        def _target():
            asyncio.run(self._run())

        self._thread = threading.Thread(target=_target, daemon=True)
        self._thread.start()

    def stop(self):
        if self._stop:
            self._stop.set()
