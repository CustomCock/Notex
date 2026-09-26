"""„Unbenutzte Bilder finden“: Liste mit Vorschau, Häkchen und „In den Papierkorb“ – nie automatisch löschen."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

from notex.core import fileops
from notex.theme.tokens import SPACING
from notex.ui import dialogs
from notex.ui.viewer_page import human_size

ROLE_PATH = Qt.ItemDataRole.UserRole + 1


class UnusedImagesDialog(QDialog):
    trashed = Signal(list)

    def __init__(self, parent: QWidget, root: Path, images: list[Path], skipped_ntx: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Unbenutzte Bilder")
        self.resize(720, 480)
        self.root = root
        info = QLabel(f"{len(images)} Bild(er), auf die keine Notiz verweist. Angekreuzte kommen in den Papierkorb."
                      if images else "Alle Bilder werden von Notizen verwendet.")
        info.setWordWrap(True)
        note = QLabel(f"{skipped_ntx} verschlüsselte Notiz(en) konnten nicht geprüft werden – Bilder, die nur dort "
                      "verlinkt sind, erscheinen trotzdem hier." if skipped_ntx else "")
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        note.setVisible(bool(skipped_ntx))
        self.list = QListWidget()
        self.list.setIconSize(QSize(64, 64))
        self.preview = QLabel()
        self.preview.setFixedSize(240, 240)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("SettingsNote")
        for path in images:
            try:
                size = human_size(path.stat().st_size)
            except OSError:
                size = "?"
            item = QListWidgetItem(f"{path.relative_to(root).as_posix()}  ·  {size}")
            item.setData(ROLE_PATH, str(path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setIcon(QIcon(self._thumb(path, 64)))
            self.list.addItem(item)
        self.list.currentItemChanged.connect(lambda item, _p: self._show(item))
        trash = QPushButton("Angekreuzte in den Papierkorb")
        trash.setObjectName("Danger")
        trash.clicked.connect(self._trash)
        trash.setEnabled(bool(images))
        close = QPushButton("Schließen")
        close.clicked.connect(self.accept)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        body.addWidget(self.preview)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(close)
        buttons.addWidget(trash)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.addWidget(info)
        layout.addWidget(note)
        layout.addLayout(body, 1)
        layout.addLayout(buttons)
        if images:
            self.list.setCurrentRow(0)

    @staticmethod
    def _thumb(path: Path, size: int) -> QPixmap:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        original = reader.size()
        if original.isValid():
            reader.setScaledSize(original.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        return QPixmap.fromImage(image) if not image.isNull() else QPixmap()

    def _show(self, item) -> None:
        if item is not None:
            self.preview.setPixmap(self._thumb(Path(item.data(ROLE_PATH)), 240))

    def _trash(self) -> None:
        chosen = [Path(self.list.item(i).data(ROLE_PATH)) for i in range(self.list.count())
                  if self.list.item(i).checkState() == Qt.CheckState.Checked]
        if not chosen:
            return
        if not dialogs.confirm(self, "In den Papierkorb", f"{len(chosen)} Bild(er) in den Papierkorb verschieben?",
                               yes="In den Papierkorb", danger=True):
            return
        done = []
        for path in chosen:
            try:
                fileops.move_to_trash(path)
                done.append(path)
            except Exception as error:  # noqa: BLE001 – send2trash wirft eigene Typen
                dialogs.warn(self, "Papierkorb", f"{path.name}: {error}")
        for i in reversed(range(self.list.count())):
            if Path(self.list.item(i).data(ROLE_PATH)) in done:
                self.list.takeItem(i)
        self.trashed.emit(done)
