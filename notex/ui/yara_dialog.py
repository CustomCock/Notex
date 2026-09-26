"""YARA „Regel testen“: Regeln aus dem Editor (auch ungespeichert) oder aus einer Datei gegen Datei/Ordner laufen
lassen. Trefferliste mit Regel, Datei, Offset, String und Treffer; Doppelklick → Hex-Ansicht am Offset.
Syntaxfehler: Zeile in der Statuszeile und im Editor rot unterwellt."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableView)

from notex.core import yara_rules as yr
from notex.theme.tokens import COLORS
from notex.ui.analysis_dialog import AnalysisDialog

HEADERS = ["Regel", "Datei", "Offset", "String", "Treffer"]
RULE_SUFFIXES = (".yar", ".yara")


class HitsModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.hits: list[yr.Hit] = []
        self.base: Path | None = None

    def load(self, hits: list[yr.Hit], base: Path) -> None:
        self.beginResetModel()
        self.hits, self.base = hits, base
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.hits)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return HEADERS[section]
        return None

    def _name(self, path: Path) -> str:
        if self.base is not None and self.base.is_dir():
            try:
                return str(path.relative_to(self.base))
            except ValueError:
                pass
        return path.name

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        hit = self.hits[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            offset = f"0x{hit.offset:08X}" if hit.offset >= 0 else "–"
            return (hit.rule, self._name(hit.file), offset, hit.identifier or "(Bedingung)",
                    yr.preview(hit.data))[index.column()]
        if role == Qt.ItemDataRole.ToolTipRole:
            parts = [str(hit.file)]
            if hit.tags:
                parts.append("Tags: " + ", ".join(hit.tags))
            parts += [f"{k}: {v}" for k, v in list(hit.meta.items())[:8]]
            return "\n".join(parts)
        return None


class YaraDialog(AnalysisDialog):
    def __init__(self, window, rule_path: Path, target: Path | None, editor=None) -> None:
        super().__init__(window, rule_path, "YARA-Regel testen")
        self.editor = editor
        self.cfg = window.config.setdefault("yara", {})
        self.head.setText(f"Regeln: {rule_path.name}" + ("  ·  aus dem Editor (auch Ungespeichertes)" if editor else ""))
        row = QHBoxLayout()
        row.addWidget(QLabel("Ziel"))
        self.target = QLineEdit(str(target) if target else self.cfg.get("last_target", ""))
        self.target.setPlaceholderText("Datei oder Ordner")
        self.target.returnPressed.connect(self.run)
        row.addWidget(self.target, 1)
        pick_file = QPushButton("Datei …")
        pick_file.clicked.connect(lambda: self._pick(folder=False))
        pick_folder = QPushButton("Ordner …")
        pick_folder.clicked.connect(lambda: self._pick(folder=True))
        self.recursive = QCheckBox("Unterordner")
        self.recursive.setChecked(bool(self.cfg.get("recursive", True)))
        self.run_button = QPushButton("Prüfen")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.run)
        for widget in (pick_file, pick_folder, self.recursive, self.run_button):
            row.addWidget(widget)
        self.body.addLayout(row)
        self.model = HitsModel()
        self.table = QTableView()
        self.table.setObjectName("AnalysisTable")
        self.table.setModel(self.model)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 180), (1, 240), (2, 100), (3, 90)):
            self.table.setColumnWidth(column, width)
        self.table.doubleClicked.connect(self._jump)
        self.table.activated.connect(self._jump)
        self.body.addWidget(self.table, 1)
        hint = QLabel("Doppelklick springt in die Hex-Ansicht (Treffer markiert). Dateien werden nur gelesen.")
        hint.setObjectName("SettingsNote")
        self.body.addWidget(hint)
        self.finish_layout()
        self.progress.setValue(0)
        self.cancel_button.setEnabled(False)
        if self.target.text():
            self.run()
        else:
            self.status.setText("Ziel wählen und „Prüfen“")

    def _pick(self, folder: bool) -> None:
        start = self.target.text() or str(self.path.parent)
        chosen = QFileDialog.getExistingDirectory(self, "Ordner prüfen", start) if folder else \
            QFileDialog.getOpenFileName(self, "Datei prüfen", start)[0]
        if chosen:
            self.target.setText(chosen)
            self.run()

    def _source(self) -> str:
        if self.editor is not None:
            return self.editor.toPlainText()
        return self.path.read_text(encoding="utf-8", errors="replace")

    def run(self) -> None:
        target = Path(self.target.text().strip())
        if not self.target.text().strip() or not target.exists():
            self.status.setText("Ziel existiert nicht")
            return
        self.status.setStyleSheet("")
        try:
            rules = yr.compile_rules(self._source(), self.path.parent)
        except yr.RuleError as error:
            self.status.setText(f"Syntaxfehler – {error}")
            self.status.setStyleSheet(f"color: {COLORS.danger};")
            self.window_.mark_yara_error(self.editor, error.line)
            return
        except (yr.YaraMissing, OSError) as error:
            self.status.setText(str(error))
            return
        self.window_.mark_yara_error(self.editor, None)
        self.cfg["last_target"], self.cfg["recursive"] = str(target), self.recursive.isChecked()
        self.cfg["last_rule"] = str(self.path)
        recursive = self.recursive.isChecked()
        self._base = target
        self.start(lambda progress, cancelled: yr.scan(rules, target, recursive, progress, cancelled))

    def show_result(self, result: yr.ScanResult) -> None:
        self.model.load(result.hits, self._base)
        rules = len({h.rule for h in result.hits})
        text = f"{result.files} Datei(en) geprüft · {result.matched_files} mit Treffern · {rules} Regel(n) · " \
               f"{len(result.hits)} Stelle(n)"
        if result.truncated:
            text += f" · nach {yr.MAX_HITS} abgeschnitten"
        if result.errors:
            text += f" · {len(result.errors)} Fehler"
            self.status.setToolTip("\n".join(result.errors[:30]))
        self.status.setText(text if result.hits else f"{result.files} Datei(en) geprüft · keine Treffer")

    def _jump(self, index) -> None:
        if not index.isValid():
            return
        hit = self.model.hits[index.row()]
        if hit.offset >= 0:
            self.window_.show_in_hex(hit.file, hit.offset, max(1, hit.length))
