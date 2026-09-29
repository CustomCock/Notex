"""Netzwerk-Scanner: Ziel und Profil eingeben, Hosts und offene Ports finden, Ergebnis als Tabelle, Speichern
(JSON + Markdown-Report in data/scans/), Vergleich mit einem früheren Scan, Skript-Export (PowerShell/Bash).

Nur für das eigene Netz. Ziele außerhalb privater Bereiche verlangen eine Bestätigung (abschaltbar in den Einstellungen).
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from notex import APP_NAME
from notex.core import fileops, scan
from notex.theme.icons import icon
from notex.theme.tokens import SPACING


class ScanThread(QThread):
    host_found = Signal(object)
    progress = Signal(int, int)
    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, targets: list[scan.Target], config: scan.ScanConfig) -> None:
        super().__init__()
        self.targets, self.config = targets, config
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            hosts = asyncio.run(scan.scan(
                self.targets, self.config,
                pinger=scan.system_ping if self.config.use_ping else None,
                progress=lambda d, t: self.progress.emit(d, t),
                cancelled=lambda: self._cancel,
                on_host=lambda h: self.host_found.emit(h)))
        except asyncio.CancelledError:
            self.finished_ok.emit([])
        except Exception as error:   # noqa: BLE001 – Fehler dezent an die UI
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        if not self._cancel:
            try:
                self._fill_macs(hosts)
            except Exception:        # noqa: BLE001 – ARP ist Beiwerk
                pass
        self.finished_ok.emit(hosts)

    @staticmethod
    def _fill_macs(hosts: list[scan.Host]) -> None:
        table = scan.arp_table()
        for host in hosts:
            if not host.mac and host.ip in table:
                host.mac = table[host.ip]


HEADERS = ["Host", "Name", "MAC", "Offene Ports", "Dienste / Banner"]


class ScanDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window_ = window
        self.cfg = window.config.setdefault("scan", {})
        self.setWindowTitle("Netzwerk-Scanner")
        self.resize(1000, 660)
        self.thread: ScanThread | None = None
        self.hosts: list[scan.Host] = []
        self.previous: list[scan.Host] | None = None
        self.targets_text = ""
        self.config: scan.ScanConfig | None = None
        self._build()

    # ---- Aufbau ---------------------------------------------------------------------------------
    def _build(self) -> None:
        self.target = QLineEdit(self.cfg.get("last_target", ""))
        self.target.setPlaceholderText("192.168.1.0/24, 10.0.0.1-10.0.0.50, host.local, …  (nur eigenes Netz)")
        self.profile = QComboBox()
        self.profile.addItem("Top-100-Ports", "top100")
        self.profile.addItem("Top-1000-Ports", "top1000")
        self.profile.addItem("Eigene Ports …", "custom")
        for name in self.cfg.get("profiles", {}):
            self.profile.addItem(f"Profil: {name}", f"saved:{name}")
        self.profile.currentIndexChanged.connect(self._profile_changed)
        self.ports = QLineEdit("22,80,443,445,3389,8080")
        self.ports.setPlaceholderText("z. B. 22,80,443 oder 1-1024")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(0.1, 10.0)
        self.timeout.setSingleStep(0.1)
        self.timeout.setValue(float(self.cfg.get("timeout", 1.0)))
        self.timeout.setSuffix(" s")
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 1000)
        self.concurrency.setValue(int(self.cfg.get("concurrency", scan.DEFAULT_CONCURRENCY)))
        self.banner = QCheckBox("Banner lesen")
        self.banner.setChecked(bool(self.cfg.get("grab_banner", True)))
        self.discover = QCheckBox("Erst Hosts finden")
        self.discover.setChecked(bool(self.cfg.get("discover", True)))
        self.use_ping = QCheckBox("auch System-ping")
        self.use_ping.setChecked(bool(self.cfg.get("use_ping", False)))

        form = QFormLayout()
        form.addRow("Ziel", self.target)
        profile_row = QHBoxLayout()
        profile_row.addWidget(self.profile)
        profile_row.addWidget(self.ports, 1)
        save_profile = QPushButton("Profil speichern")
        save_profile.clicked.connect(self._save_profile)
        profile_row.addWidget(save_profile)
        form.addRow("Ports", profile_row)
        options = QHBoxLayout()
        options.addWidget(QLabel("Timeout"))
        options.addWidget(self.timeout)
        options.addWidget(QLabel("Parallel"))
        options.addWidget(self.concurrency)
        options.addWidget(self.banner)
        options.addWidget(self.discover)
        options.addWidget(self.use_ping)
        options.addStretch(1)
        form.addRow("Optionen", options)

        self.start_button = QPushButton(icon("radar"), "Scan starten")
        self.start_button.setDefault(True)
        self.start_button.clicked.connect(self.start)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        run_row = QHBoxLayout()
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        run_row.addStretch(1)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        for column, width in ((0, 140), (1, 180), (2, 150), (3, 160)):
            self.table.setColumnWidth(column, width)

        self.status = QLabel("Ziel eingeben und „Scan starten“. Es werden vollständige TCP-Verbindungen aufgebaut "
                             "(kein SYN-Scan) – nur im eigenen Netz.")
        self.status.setObjectName("SettingsNote")
        self.status.setWordWrap(True)

        self.save_button = self._tool("Speichern (JSON + Report)", self._save)
        self.compare_button = self._tool("Mit Scan vergleichen …", self._compare)
        self.export_button = self._tool("Als Skript exportieren …", self._export)
        self.to_ip_button = self._tool("An IP-Übersicht geben", self._to_ip)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addWidget(self.save_button)
        footer.addWidget(self.compare_button)
        footer.addWidget(self.export_button)
        footer.addWidget(self.to_ip_button)
        footer.addStretch(1)
        footer.addWidget(close)
        self._set_result_buttons(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addLayout(form)
        layout.addLayout(run_row)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.status)
        layout.addLayout(footer)
        self._profile_changed()

    def _tool(self, text: str, slot) -> QPushButton:
        button = QPushButton(text)
        button.clicked.connect(slot)
        return button

    def _set_result_buttons(self, on: bool) -> None:
        for button in (self.save_button, self.compare_button, self.export_button, self.to_ip_button):
            button.setEnabled(on)

    # ---- Profile --------------------------------------------------------------------------------
    def _profile_changed(self) -> None:
        data = self.profile.currentData()
        if data == "custom":
            self.ports.setEnabled(True)
            return
        self.ports.setEnabled(False)
        if data in ("top100", "top1000"):
            self.ports.setText("top100" if data == "top100" else "top1000")
        elif isinstance(data, str) and data.startswith("saved:"):
            self.ports.setText(self.cfg.get("profiles", {}).get(data[6:], ""))

    def _save_profile(self) -> None:
        from notex.ui import dialogs
        name = dialogs.ask_text(self, "Profil speichern", "Name des Profils:", "")
        if not name:
            return
        try:
            ports = scan.parse_ports(self.ports.text())
        except ValueError as error:
            self.status.setText(f"Ports ungültig: {error}")
            return
        self.cfg.setdefault("profiles", {})[name] = ",".join(map(str, ports))
        if self.profile.findData(f"saved:{name}") < 0:
            self.profile.addItem(f"Profil: {name}", f"saved:{name}")
        self.status.setText(f"Profil „{name}“ gespeichert ({len(ports)} Ports)")

    # ---- Scan -----------------------------------------------------------------------------------
    def start(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            return
        try:
            ports = scan.parse_ports(self.ports.text())
        except ValueError as error:
            self.status.setText(f"Ports ungültig: {error}")
            return
        targets, warnings = scan.parse_targets(self.target.text(), limit=self._limit())
        if not targets:
            self.status.setText("Keine gültigen Ziele. " + (" ".join(warnings) if warnings else ""))
            return
        if not scan.all_private(targets) and not self._confirm_public(targets):
            return
        if len(targets) > 512 and not self._confirm_size(len(targets)):
            return
        self.targets_text = self.target.text().strip()
        self.config = scan.ScanConfig(ports=ports, timeout=self.timeout.value(),
                                      concurrency=self.concurrency.value(), grab_banner=self.banner.isChecked(),
                                      discover=self.discover.isChecked(), use_ping=self.use_ping.isChecked())
        self.cfg.update(last_target=self.targets_text, timeout=self.timeout.value(),
                        concurrency=self.concurrency.value(), grab_banner=self.banner.isChecked(),
                        discover=self.discover.isChecked(), use_ping=self.use_ping.isChecked())
        self.hosts = []
        self.table.setRowCount(0)
        self._set_result_buttons(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        note = f"Scanne {len(targets)} Ziel(e) × {len(ports)} Port(s) …"
        self.status.setText(note + (" · " + " ".join(warnings) if warnings else ""))
        self.thread = ScanThread(targets, self.config)
        self.thread.host_found.connect(self._host_found)
        self.thread.progress.connect(self._progress)
        self.thread.finished_ok.connect(self._finished)
        self.thread.failed.connect(self._failed)
        self.thread.start()

    def _limit(self) -> int:
        return int(self.cfg.get("max_targets", scan.MAX_TARGETS))

    def _confirm_public(self, targets) -> bool:
        if self.cfg.get("confirm_public") is False:
            return True
        public = [t.ip for t in targets if not scan.is_private(t.ip)][:5]
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Ziel außerhalb des privaten Netzes")
        box.setText("Es sind Ziele dabei, die NICHT in einem privaten Bereich liegen:\n\n" + ", ".join(public)
                    + ("…" if len(public) == 5 else "")
                    + "\n\nScanne nur Systeme, für die du eine Erlaubnis hast. Fortfahren?")
        never = QCheckBox("Nicht mehr fragen")
        box.setCheckBox(never)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        ok = box.exec() == QMessageBox.StandardButton.Yes
        if ok and never.isChecked():
            self.cfg["confirm_public"] = False
        return ok

    def _confirm_size(self, count: int) -> bool:
        from notex.ui import dialogs
        return dialogs.confirm(self, "Großer Scan", f"{count} Ziele – das kann dauern. Fortfahren?")

    def _host_found(self, host: scan.Host) -> None:
        if host.alive or host.ports:
            self.hosts.append(host)
            self._append_row(host)

    def _append_row(self, host: scan.Host) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        ports = ", ".join(str(p) for p in host.open_ports) or "–"
        services = "; ".join(f"{p.port} {p.service}".strip() + (f" · {p.banner}" if p.banner else "")
                             for p in host.ports)
        for column, text in enumerate((host.ip, host.hostname, host.mac, ports, services)):
            item = QTableWidgetItem(text)
            if column == 4 and services:
                item.setToolTip(services)
            self.table.setItem(row, column, item)

    def _progress(self, done: int, total: int) -> None:
        self.status.setText(f"{done}/{total} Ziele geprüft · {len(self.hosts)} aktiv")

    def _finished(self, hosts: list) -> None:
        if hosts:
            self.hosts = [h for h in hosts if h.alive or h.ports]
            self.table.setRowCount(0)
            for host in sorted(self.hosts, key=lambda h: tuple(int(x) for x in h.ip.split(".")) if "." in h.ip else ()):
                self._append_row(host)
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._set_result_buttons(bool(self.hosts))
        total_ports = sum(len(h.ports) for h in self.hosts)
        self.status.setText(f"Fertig: {len(self.hosts)} aktive Host(s), {total_ports} offene Ports. "
                            "TCP-Connect-Scan – kein SYN, keine OS-Erkennung, kein UDP.")
        self.thread = None

    def _failed(self, message: str) -> None:
        self.start_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.status.setText(f"Scan fehlgeschlagen: {message}")
        self.thread = None

    def cancel(self) -> None:
        if self.thread is not None:
            self.thread.cancel()
            self.status.setText("Abbruch … (laufende Verbindungen werden noch beendet)")

    # ---- Ergebnis weiterverarbeiten -------------------------------------------------------------
    def _scans_dir(self) -> Path:
        folder = self.window_.root / "scans"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _save(self) -> None:
        import json
        if not self.hosts or self.config is None:
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        folder = self._scans_dir()
        try:
            data = json.dumps(scan.to_dict(self.hosts, self.config, self.targets_text), indent=2, ensure_ascii=False)
            fileops.atomic_write_bytes(folder / f"scan-{stamp}.json", data.encode("utf-8"))
            report = scan.to_markdown_report(self.hosts, self.config, self.targets_text)
            fileops.atomic_write_bytes(folder / f"scan-{stamp}.md", report.encode("utf-8"))
        except OSError as error:
            self.status.setText(f"Nicht gespeichert: {error}")
            return
        self.window_.file_index.request_rescan()
        self.status.setText(f"Gespeichert in data/scans/scan-{stamp}.json und .md")

    def _compare(self) -> None:
        if not self.hosts:
            return
        start = str(self._scans_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Früheren Scan wählen", start, f"{APP_NAME}-Scan (*.json)")
        if not path:
            return
        try:
            previous = scan.load(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError, scan.ScanError) as error:
            self.status.setText(f"Nicht lesbar: {error}")
            return
        diff = scan.compare(previous, self.hosts)
        ComparisonDialog(self, diff, Path(path).name).show()

    def _export(self) -> None:
        if self.config is None and not self.target.text().strip():
            return
        try:
            ports = scan.parse_ports(self.ports.text())
        except ValueError as error:
            self.status.setText(f"Ports ungültig: {error}")
            return
        ExportDialog(self, self.target.text().strip(), ports, self.timeout.value(), self.discover.isChecked()).show()

    def _to_ip(self) -> None:
        if not self.hosts:
            return
        note = scan.as_ip_note(self.hosts)
        if getattr(self.window_, "ip_index", None) is not None:
            self.window_.ip_index.extra["scan"] = self._as_assignments()
            self.window_._mark_ip_conflicts()
            self.window_.show_ip_overview()
            self.status.setText("Scan-Ergebnis als Quelle in der IP-Übersicht ergänzt.")
        else:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(note)
            self.status.setText("Modul „IP-Konflikte“ ist aus – Tabelle in die Zwischenablage kopiert.")

    def _as_assignments(self) -> list:
        from notex.core import ipmap
        items = []
        for host in self.hosts:
            name = host.hostname or f"host-{host.ip.replace('.', '-')}"
            items.append(ipmap.Assignment(host.ip, name, Path("(Netzwerk-Scan)"), 0))
        return items

    def closeEvent(self, event) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(3000)
        super().closeEvent(event)


class ComparisonDialog(QDialog):
    def __init__(self, parent, diff: scan.Diff, name: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Vergleich mit {name}")
        self.resize(640, 480)
        from PySide6.QtWidgets import QTextBrowser
        view = QTextBrowser()
        view.setMarkdown(scan.diff_to_markdown(diff))
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)


class ExportDialog(QDialog):
    def __init__(self, parent, targets_text: str, ports: list[int], timeout: float, ping_first: bool) -> None:
        super().__init__(parent)
        self.parent_ = parent
        self.targets_text, self.ports, self.timeout, self.ping_first = targets_text, ports, timeout, ping_first
        self.setWindowTitle("Scan als Skript exportieren")
        self.resize(760, 560)
        from PySide6.QtWidgets import QPlainTextEdit
        self.kind = QComboBox()
        self.kind.addItem("PowerShell (.ps1)", "ps")
        self.kind.addItem("Bash (.sh)", "sh")
        self.kind.currentIndexChanged.connect(self._render)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setObjectName("CodeView")
        save = QPushButton("Speichern …")
        save.clicked.connect(self._save)
        copy = QPushButton("Kopieren")
        copy.clicked.connect(self._copy)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        note = QLabel("Eigenständige Skripte mit denselben Zielen und Ports, CSV-Ausgabe. Nur Bordmittel, keine "
                      "Admin-Rechte. Header enthält den Ausführungshinweis.")
        note.setObjectName("SettingsNote")
        note.setWordWrap(True)
        top = QHBoxLayout()
        top.addWidget(self.kind)
        top.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.view, 1)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)
        self._render()

    def _script(self) -> str:
        from notex.core import scan_export
        if self.kind.currentData() == "ps":
            return scan_export.powershell(self.targets_text, self.ports, self.timeout, self.ping_first)
        return scan_export.bash(self.targets_text, self.ports, self.timeout, self.ping_first)

    def _render(self) -> None:
        self.view.setPlainText(self._script())

    def _copy(self) -> None:
        from PySide6.QtGui import QGuiApplication
        QGuiApplication.clipboard().setText(self._script())

    def _save(self) -> None:
        suffix = ".ps1" if self.kind.currentData() == "ps" else ".sh"
        start = str(self.parent_.window_.root / f"scan{suffix}")
        path, _ = QFileDialog.getSaveFileName(self, "Skript speichern", start, f"Skript (*{suffix})")
        if not path:
            return
        try:
            fileops.atomic_write_bytes(Path(path), self._script().encode("utf-8"))
        except OSError as error:
            QMessageBox.warning(self, "Speichern", str(error))
            return
        self.close()


