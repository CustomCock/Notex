"""Einzelinstanz über QLocalServer/QLocalSocket.

Beim Start: Versuch, eine laufende Instanz zu erreichen. Klappt das, schicken wir ihr die
Pfade und beenden uns. Klappt es nicht, werden wir selbst der Server. Starten zwei Instanzen
gleichzeitig (Race), scheitert bei einer das listen(); sie versucht dann noch einmal den Weg
als Client, bevor sie aufgibt und ein eigenes Fenster öffnet.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from notex.core.ipc import decode_open_request, encode_open_request

CONNECT_TIMEOUT_MS = 300


def send_to_running_instance(name: str, paths: list[Path | str]) -> bool:
    """True, wenn eine laufende Instanz die Pfade übernommen hat."""
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
        return False
    written = socket.write(encode_open_request(paths)) > 0
    socket.flush()
    socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
    socket.waitForReadyRead(CONNECT_TIMEOUT_MS)   # kurze Bestätigung ("ok") abwarten
    socket.disconnectFromServer()
    return written


class InstanceServer(QObject):
    open_requested = Signal(list)   # list[str]

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_connection)
        self.listening = False

    def start(self) -> bool:
        # Ein verwaister Socket (Absturz) würde listen() blockieren – vorher aufräumen.
        # Läuft wirklich noch eine Instanz, hat send_to_running_instance() schon gegriffen.
        QLocalServer.removeServer(self.name)
        self.listening = self._server.listen(self.name)
        return self.listening

    def _on_connection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        buffer = bytearray()

        def read() -> None:
            buffer.extend(bytes(socket.readAll()))
            if b"\n" in buffer:
                paths = decode_open_request(bytes(buffer))
                socket.write(b"ok\n")
                socket.flush()
                socket.disconnectFromServer()
                if paths:
                    self.open_requested.emit(paths)

        socket.readyRead.connect(read)
        socket.disconnected.connect(socket.deleteLater)
        if socket.bytesAvailable():
            read()

    def stop(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self.name)
