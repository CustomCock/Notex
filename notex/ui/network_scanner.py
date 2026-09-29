"""Netzwerk-Scanner (Geräteübersicht, wie „Advanced IP Scanner") – eigenes Subnetz automatisch, Live-Tabelle mit
Status/Name/IP/MAC/Hersteller/Kommentar/Diensten/Antwortzeit, Host-Aktionen, Favoriten/Kommentare, Export.

Nutzt die Scan-Engine (core/scan), die OUI-Herstellerliste (core/oui) und die Netz-Erkennung (core/netdetect).
Alle Netzzugriffe laufen im Worker-Thread; nur auf ausdrückliche Aktion des Nutzers. Nur für das eigene Netz.
"""
from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QGuiApplication, QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QInputDialog,
                               QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from notex.core import netdetect, oui, scan
from notex.theme.icons import icon
from notex.theme.tokens import COLORS, SPACING

HEADERS = ["", "Name", "IP", "MAC", "Hersteller", "Kommentar", "Dienste", "ms"]
COL_STATUS, COL_NAME, COL_IP, COL_MAC, COL_VENDOR, COL_COMMENT, COL_SERVICES, COL_RTT = range(8)

# Portnummer → kurzer Dienstname für die „Dienste"-Chips
SERVICE_CHIPS = {80: "HTTP", 443: "HTTPS", 22: "SSH", 3389: "RDP", 445: "SMB", 139: "SMB", 21: "FTP",
                 23: "Telnet", 25: "SMTP", 53: "DNS", 3306: "MySQL", 5432: "PostgreSQL", 8080: "HTTP-Alt",
                 631: "Drucker", 9100: "Drucker", 5900: "VNC", 161: "SNMP", 548: "AFP", 111: "RPC"}

PROFILES = {
    "schnell": {"label": "Schnell (Top-100, kein Banner)", "ports": "top100", "banner": False, "concurrency": 400},
    "standard": {"label": "Standard (Top-100, Banner)", "ports": "top100", "banner": True, "concurrency": 200},
    "gruendlich": {"label": "Gründlich (Top-1000, Banner)", "ports": "top1000", "banner": True, "concurrency": 200},
}


@dataclass
class Device:
    ip: str
    name: str = ""
    mac: str = ""
    vendor: str = ""
    ports: list[int] = field(default_factory=list)
    rtt_ms: int | None = None
    alive: bool = True

    @property
    def key(self) -> str:
        return self.mac or self.ip

    def services(self) -> str:
        chips = []
        for port in self.ports:
            label = SERVICE_CHIPS.get(port)
            if label and label not in chips:
                chips.append(label)
        extra = len([p for p in self.ports if p not in SERVICE_CHIPS])
        if extra:
            chips.append(f"+{extra}")
        return ", ".join(chips)


class ScannerThread(QThread):
    device = Signal(object)          # Device (auch Aktualisierung – nach IP zusammengeführt)
    progress = Signal(int, int)
    done = Signal()
    failed = Signal(str)

    def __init__(self, targets, config, *, netbios: bool, use_ping: bool) -> None:
        super().__init__()
        self.targets, self.config = targets, config
        self.netbios, self.use_ping = netbios, use_ping
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            hosts = asyncio.run(scan.scan(
                self.targets, self.config,
                pinger=scan.system_ping if self.use_ping else None,
                progress=lambda d, t: self.progress.emit(d, t),
                cancelled=lambda: self._cancel,
                on_host=lambda h: self.device.emit(Device(h.ip, h.hostname, h.mac, "", h.open_ports, None, True))))
        except Exception as error:              # noqa: BLE001
            self.failed.emit(f"{type(error).__name__}: {error}")
            return
        if self._cancel:
            self.done.emit()
            return
        # Anreichern: MAC (ARP), Hersteller, NetBIOS-Name, Antwortzeit
        try:
            arp = scan.arp_table()
        except Exception:                        # noqa: BLE001
            arp = {}
        for host in hosts:
            if self._cancel:
                break
            mac = host.mac or arp.get(host.ip, "")
            name = host.hostname
            if not name and self.netbios:
                name = _netbios_name(host.ip) or ""
            rtt = _rtt(host.ip, host.open_ports)
            self.device.emit(Device(host.ip, name, mac, oui.vendor_label(mac) if mac else "",
                                    host.open_ports, rtt, True))
        self.done.emit()


class JobThread(QThread):
    """Einzelne Host-Aktion (Ping, Traceroute) im Hintergrund – nie im UI-Thread, Fehler als Text."""
    finished_job = Signal(object, str)       # Ergebnis, Fehlertext

    def __init__(self, job, parent=None) -> None:
        super().__init__(parent)             # Eltern = Hauptfenster: überlebt das Schließen des Dialogs
        self.job = job
        self.finished.connect(self.deleteLater)

    def run(self) -> None:
        try:
            self.finished_job.emit(self.job(), "")
        except Exception as error:            # noqa: BLE001 – im Dialog melden statt lautlos abbrechen
            self.finished_job.emit(None, f"{type(error).__name__}: {error}")


def show_text(parent, title: str, text: str) -> QDialog:
    """Kleines Textfenster (nicht modal) für Befehlsausgaben – markier- und kopierbar."""
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QPlainTextEdit
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dialog.resize(640, 420)
    layout = QVBoxLayout(dialog)
    view = QPlainTextEdit(text)
    view.setReadOnly(True)
    font = QFont("JetBrains Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    view.setFont(font)
    layout.addWidget(view)
    row = QHBoxLayout()
    copy = QPushButton("Kopieren")
    copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(view.toPlainText()))
    close = QPushButton("Schließen")
    close.clicked.connect(dialog.close)
    row.addStretch(1)
    row.addWidget(copy)
    row.addWidget(close)
    layout.addLayout(row)
    dialog.show()
    return dialog


def _rtt(ip: str, ports: list[int]) -> int | None:
    """Grobe Antwortzeit: TCP-Connect zu einem offenen Port (oder gängigen Ports) messen."""
    candidates = ports[:1] or [80, 443, 22, 445]
    for port in candidates:
        start = time.monotonic()
        try:
            with socket.create_connection((ip, port), timeout=1.0):
                return int((time.monotonic() - start) * 1000)
        except OSError:
            continue
    return None


def _netbios_name(ip: str) -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(1.0)
            sock.sendto(netdetect.build_nbstat_request(), (ip, 137))
            data, _ = sock.recvfrom(2048)
        return netdetect.parse_nbstat_response(data)
    except OSError:
        return None


class NetworkScannerDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window_ = window
        self.cfg = window.config.setdefault("scan", {})
        self.cfg.setdefault("comments", {})
        self.cfg.setdefault("favorites", [])
        self.setWindowTitle("Netzwerk-Scanner")
        self.resize(1080, 680)
        self.thread: ScannerThread | None = None
        self._jobs: list[JobThread] = []
        self.devices: dict[str, Device] = {}
        self._build()
        self._autofill_target()

    # ---- Aufbau ---------------------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.md)
        layout.setSpacing(SPACING.sm)

        top = QHBoxLayout()
        self.target = QLineEdit(self.cfg.get("last_target", ""))
        self.target.setPlaceholderText("192.168.1.0/24, 10.0.0.1-50 …  (eigenes Netz)")
        self.profile = QComboBox()
        for key, meta in PROFILES.items():
            self.profile.addItem(meta["label"], key)
        self.profile.setCurrentIndex(max(0, self.profile.findData(self.cfg.get("profile", "standard"))))
        self.start_button = QPushButton(icon("radar"), "Scannen")
        self.start_button.clicked.connect(self._toggle_scan)
        top.addWidget(QLabel("Ziel"))
        top.addWidget(self.target, 1)
        top.addWidget(self.profile)
        top.addWidget(self.start_button)
        layout.addLayout(top)

        opts = QHBoxLayout()
        self.exclude = QLineEdit(self.cfg.get("exclude", ""))
        self.exclude.setPlaceholderText("Ausschließen: 192.168.1.1, .20-30 …")
        self.opt_netbios = QCheckBox("NetBIOS-Namen")
        self.opt_netbios.setChecked(self.cfg.get("netbios", True))
        self.opt_ping = QCheckBox("System-Ping")
        self.opt_ping.setChecked(self.cfg.get("use_ping", False))
        self.only_alive = QCheckBox("nur erreichbare")
        self.only_alive.setChecked(True)
        self.only_alive.toggled.connect(self._refresh_table)
        opts.addWidget(self.exclude, 1)
        opts.addWidget(self.opt_netbios)
        opts.addWidget(self.opt_ping)
        opts.addWidget(self.only_alive)
        layout.addLayout(opts)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtern: Name, IP, MAC, Hersteller, Dienst …")
        self.filter.textChanged.connect(self._refresh_table)
        layout.addWidget(self.filter)

        self.table = QTableWidget(0, len(HEADERS))
        self.table.setObjectName("AnalysisTable")
        self.table.setHorizontalHeaderLabels(HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(COL_STATUS, 24)
        self.table.horizontalHeader().setSectionResizeMode(COL_COMMENT, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(self._on_double)
        # Spalten ein-/ausblenden per Rechtsklick auf den Kopf
        header = self.table.horizontalHeader()
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_menu)
        self._restore_columns()
        layout.addWidget(self.table, 1)

        self.progress = QProgressBar()
        self.progress.setTextVisible(True)
        layout.addWidget(self.progress)

        footer = QHBoxLayout()
        self.status = QLabel("Bereit")
        self.status.setObjectName("SettingsNote")
        export = QPushButton(icon("file-output"), "Export …")
        export.clicked.connect(self._export)
        to_ip = QPushButton("An IP-Übersicht")
        to_ip.clicked.connect(self._to_ip_overview)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer.addWidget(self.status, 1)
        footer.addWidget(to_ip)
        footer.addWidget(export)
        footer.addWidget(close)
        layout.addLayout(footer)

    def _autofill_target(self) -> None:
        if self.target.text().strip():
            return
        adapters = netdetect.local_adapters()
        if adapters:
            self.target.setText(adapters[0].cidr)
            if len(adapters) > 1:
                self.target.setToolTip("Weitere Netze: " + ", ".join(a.cidr for a in adapters[1:]))

    # ---- Scan -----------------------------------------------------------------------------------
    def _toggle_scan(self) -> None:
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.start_button.setText("Abbrechen …")
            return
        targets_text = self.target.text().strip()
        if not targets_text:
            self.status.setText("Erst ein Ziel eingeben (z. B. 192.168.1.0/24)")
            return
        targets, warnings = scan.parse_targets(targets_text)     # (Ziele, Warnungen) – nie eine Exception
        if not targets:
            self.status.setText("Keine gültigen Ziele. " + " ".join(warnings))
            return
        excluded = netdetect.parse_exclusions(self.exclude.text())
        if excluded:
            targets = [t for t in targets if t.ip not in excluded]
        if not targets:
            QMessageBox.information(self, "Ziel", "Keine Adressen übrig (alles ausgeschlossen?).")
            return
        if not scan.all_private(targets) and not self._confirm_public():
            return
        meta = PROFILES[self.profile.currentData()]
        config = scan.ScanConfig(ports=scan.parse_ports(meta["ports"]), grab_banner=meta["banner"],
                                 concurrency=meta["concurrency"], discover=True, reverse_dns=True,
                                 use_ping=self.opt_ping.isChecked())
        self.cfg.update({"last_target": targets_text, "profile": self.profile.currentData(),
                         "exclude": self.exclude.text(), "netbios": self.opt_netbios.isChecked(),
                         "use_ping": self.opt_ping.isChecked()})
        self.devices.clear()
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)
        self.progress.setRange(0, len(targets))
        self.progress.setValue(0)
        self.status.setText(f"Scanne {len(targets)} Adressen …" + (" · " + " ".join(warnings) if warnings else ""))
        self.start_button.setText("Stopp")
        self.thread = ScannerThread(targets, config, netbios=self.opt_netbios.isChecked(),
                                    use_ping=self.opt_ping.isChecked())
        self.thread.device.connect(self._on_device)
        self.thread.progress.connect(lambda d, t: self.progress.setValue(d))
        self.thread.failed.connect(self._on_failed)
        self.thread.done.connect(self._on_done)
        self.thread.start()

    def _confirm_public(self) -> bool:
        if self.cfg.get("skip_public_warning"):
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Öffentliches Ziel")
        box.setText("Das Ziel liegt außerhalb privater Netze. Nur Systeme scannen, für die du berechtigt bist.")
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        remember = QCheckBox("Nicht mehr fragen")
        box.setCheckBox(remember)
        ok = box.exec() == QMessageBox.StandardButton.Yes
        if ok and remember.isChecked():
            self.cfg["skip_public_warning"] = True
        return ok

    def _on_device(self, device: Device) -> None:
        existing = self.devices.get(device.ip)
        if existing:                            # Anreicherung: Felder nur ergänzen
            existing.name = device.name or existing.name
            existing.mac = device.mac or existing.mac
            existing.vendor = device.vendor or existing.vendor
            existing.ports = device.ports or existing.ports
            existing.rtt_ms = device.rtt_ms if device.rtt_ms is not None else existing.rtt_ms
        else:
            self.devices[device.ip] = device
        self._refresh_table()

    def _on_done(self) -> None:
        self.start_button.setText("Scannen")
        self.table.setSortingEnabled(True)
        alive = sum(1 for d in self.devices.values() if d.alive)
        self.status.setText(f"{alive} Geräte gefunden")
        self.progress.setValue(self.progress.maximum())

    def _on_failed(self, message: str) -> None:
        self.start_button.setText("Scannen")
        self.table.setSortingEnabled(True)
        self.status.setText(f"Scan abgebrochen: {message}")

    def _start_job(self, job, on_result) -> JobThread:
        worker = JobThread(job, self.window_)

        def finished(result, error: str) -> None:
            if worker in self._jobs:
                self._jobs.remove(worker)
            on_result(result, error)

        worker.finished_job.connect(finished)
        self._jobs.append(worker)
        worker.start()
        return worker

    # ---- Tabelle --------------------------------------------------------------------------------
    def _visible_devices(self) -> list[Device]:
        needle = self.filter.text().lower()
        out = []
        for device in sorted(self.devices.values(), key=lambda d: _ip_key(d.ip)):
            if self.only_alive.isChecked() and not device.alive:
                continue
            if needle and needle not in " ".join([device.name, device.ip, device.mac, device.vendor,
                                                   device.services()]).lower():
                continue
            out.append(device)
        return out

    def _refresh_table(self) -> None:
        shown = self._visible_devices()
        self.table.setRowCount(len(shown))
        comments = self.cfg.get("comments", {})
        favorites = set(self.cfg.get("favorites", []))
        for row, device in enumerate(shown):
            star = "★ " if device.key in favorites else ""
            values = ["●", star + device.name, device.ip, device.mac, device.vendor,
                      comments.get(device.key, ""), device.services(),
                      str(device.rtt_ms) if device.rtt_ms is not None else ""]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == COL_STATUS:
                    item.setForeground(QColor(COLORS.success if device.alive else COLORS.text_faint))
                    item.setData(Qt.ItemDataRole.UserRole, device.ip)
                self.table.setItem(row, col, item)

    def _selected(self) -> Device | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, COL_STATUS)
        ip = item.data(Qt.ItemDataRole.UserRole) if item else None
        return self.devices.get(ip) if ip else None

    # ---- Spalten ein/aus + Breiten -------------------------------------------------------------
    def _header_menu(self, pos) -> None:
        menu = QMenu(self)
        for col in range(1, len(HEADERS)):
            act = menu.addAction(HEADERS[col] or "?")
            act.setCheckable(True)
            act.setChecked(not self.table.isColumnHidden(col))
            act.toggled.connect(lambda on, c=col: (self.table.setColumnHidden(c, not on), self._save_columns()))
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def _restore_columns(self) -> None:
        hidden = self.cfg.get("hidden_columns", [])
        widths = self.cfg.get("column_widths", {})
        for col in range(len(HEADERS)):
            if col in hidden:
                self.table.setColumnHidden(col, True)
            if str(col) in widths and col != COL_COMMENT:
                self.table.setColumnWidth(col, int(widths[str(col)]))

    def _save_columns(self) -> None:
        self.cfg["hidden_columns"] = [c for c in range(len(HEADERS)) if self.table.isColumnHidden(c)]
        self.cfg["column_widths"] = {str(c): self.table.columnWidth(c) for c in range(len(HEADERS))}

    def closeEvent(self, event) -> None:
        self._save_columns()
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(2000)
        for worker in list(self._jobs):          # laufen zu Ende (Timeout im Befehl), Ergebnis wird verworfen
            worker.finished_job.disconnect()
        self._jobs.clear()
        super().closeEvent(event)

    # ---- Host-Aktionen --------------------------------------------------------------------------
    def _on_double(self, _index) -> None:
        device = self._selected()
        if device:
            self._open_browser(device)

    def _menu(self, pos) -> None:
        device = self._selected()
        if device is None:
            return
        menu = QMenu(self)
        if {80, 443, 8080} & set(device.ports):
            menu.addAction(icon("globe"), "Im Browser öffnen", lambda: self._open_browser(device))
        if 3389 in device.ports and sys.platform.startswith("win"):
            menu.addAction("Remotedesktop (RDP)", lambda: self._run(["mstsc", f"/v:{device.ip}"]))
        if {139, 445} & set(device.ports):
            menu.addAction(icon("folder-open"), "Freigaben öffnen (\\\\host)",
                           lambda: self._open_share(device))
        if 22 in device.ports:
            menu.addAction("SSH im Terminal", lambda: self._open_ssh(device))
        menu.addSeparator()
        menu.addAction(icon("radar"), "Ping", lambda: self._ping(device))
        menu.addAction("Traceroute", lambda: self._traceroute(device))
        menu.addAction("Ports vertiefen (Top-1000)", lambda: self._deep_scan(device))
        if self.window_.registry.get("rdap:lookup") is not None and not scan.is_private(device.ip):
            menu.addAction(icon("globe-lock"), "RDAP / ASN", lambda: self.window_.rdap_lookup(device.ip))
        if device.mac:
            menu.addAction("Wake-on-LAN", lambda: self._wol(device))
            if sys.platform.startswith("win"):
                menu.addAction("Herunterfahren (Remote) …", lambda: self._remote_power(device, "/s"))
                menu.addAction("Neustart (Remote) …", lambda: self._remote_power(device, "/r"))
        menu.addSeparator()
        menu.addAction(icon("pencil"), "Kommentar …", lambda: self._comment(device))
        fav = "Aus Favoriten" if device.key in self.cfg.get("favorites", []) else "Zu Favoriten"
        menu.addAction(icon("bookmark"), fav, lambda: self._toggle_favorite(device))
        copy = menu.addMenu(icon("copy"), "Kopieren")
        copy.addAction("IP", lambda: QGuiApplication.clipboard().setText(device.ip))
        copy.addAction("MAC", lambda: QGuiApplication.clipboard().setText(device.mac))
        copy.addAction("Name", lambda: QGuiApplication.clipboard().setText(device.name))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_browser(self, device: Device) -> None:
        scheme = "https" if 443 in device.ports and 80 not in device.ports else "http"
        QDesktopServices.openUrl(QUrl(f"{scheme}://{device.ip}"))

    def _open_share(self, device: Device) -> None:
        target = f"\\\\{device.ip}" if sys.platform.startswith("win") else f"smb://{device.ip}"
        QDesktopServices.openUrl(QUrl.fromLocalFile(target) if sys.platform.startswith("win") else QUrl(target))

    def _open_ssh(self, device: Device) -> None:
        if sys.platform.startswith("win"):
            self._run(["cmd", "/c", "start", "", "ssh", device.ip])
        elif sys.platform == "darwin":
            self._run(["open", f"ssh://{device.ip}"])
        else:
            for term in (["x-terminal-emulator", "-e", f"ssh {device.ip}"], ["gnome-terminal", "--", "ssh", device.ip]):
                if self._run(term):
                    return

    def _ping(self, device: Device) -> None:
        self.status.setText(f"Ping an {device.ip} …")

        def done(ok, error: str) -> None:
            self.status.setText(f"Ping {device.ip}: Fehler – {error}" if error
                                else f"{device.ip}: {'erreichbar' if ok else 'keine Antwort'}")
        self._start_job(lambda: scan.system_ping(device.ip, timeout=2.0), done)

    def _traceroute(self, device: Device) -> None:
        """Im Hintergrund ausführen, Ausgabe in einem Textfenster zeigen (vorher: Konsole ohne sichtbare Ausgabe)."""
        self.status.setText(f"Traceroute zu {device.ip} läuft … (bis zu {int(scan.TRACE_TIMEOUT)} s)")

        def done(output, error: str) -> None:
            self.status.setText(f"Traceroute zu {device.ip} fertig" if not error else f"Traceroute: {error}")
            show_text(self, f"Traceroute zu {device.ip}", output if not error else f"Fehler: {error}")
        self._start_job(lambda: scan.traceroute(device.ip), done)

    def _deep_scan(self, device: Device) -> None:
        self.target.setText(device.ip)
        self.profile.setCurrentIndex(max(0, self.profile.findData("gruendlich")))
        self._toggle_scan()

    def _wol(self, device: Device) -> None:
        try:
            netdetect.send_wol(device.mac)
            self.status.setText(f"Wake-on-LAN an {device.mac} gesendet")
        except (OSError, ValueError) as error:
            self.status.setText(f"WoL fehlgeschlagen: {error}")

    def _remote_power(self, device: Device, flag: str) -> None:
        action = "herunterfahren" if flag == "/s" else "neu starten"
        if QMessageBox.warning(self, "Remote-Befehl",
                               f"„{device.name or device.ip}“ wirklich {action}?\n"
                               "Nur mit Administratorrechten und Erlaubnis. Kann laufende Arbeit zerstören.",
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self._run(["shutdown", flag, "/m", f"\\\\{device.ip}", "/t", "30"])

    def _comment(self, device: Device) -> None:
        text, ok = QInputDialog.getText(self, "Kommentar", f"Kommentar für {device.ip}:",
                                        text=self.cfg["comments"].get(device.key, ""))
        if ok:
            self.cfg["comments"][device.key] = text.strip()
            self._refresh_table()

    def _toggle_favorite(self, device: Device) -> None:
        favorites = self.cfg.setdefault("favorites", [])
        if device.key in favorites:
            favorites.remove(device.key)
        else:
            favorites.append(device.key)
        self._refresh_table()

    def _to_ip_overview(self) -> None:
        self.window_.show_ip_overview()

    def _run(self, command: list[str]) -> bool:
        try:
            subprocess.Popen(command)
            return True
        except (OSError, subprocess.SubprocessError) as error:
            self.status.setText(f"Konnte nicht starten: {error}")
            return False

    # ---- Export ---------------------------------------------------------------------------------
    def _export(self) -> None:
        if not self.devices:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Scan exportieren", str(Path(self.cfg.get("last_target", "scan")).name or "scan"),
            "CSV (*.csv);;JSON (*.json);;Markdown (*.md);;HTML (*.html);;PDF (*.pdf)")
        if not path:
            return
        devices = self._visible_devices()
        try:
            if path.endswith(".csv"):
                _export_csv(Path(path), devices, self.cfg.get("comments", {}))
            elif path.endswith(".json"):
                _export_json(Path(path), devices, self.cfg.get("comments", {}))
            else:
                md = _export_markdown(devices, self.cfg.get("comments", {}))
                from notex.core import export as core_export
                from notex.ui import export_service
                meta = core_export.ExportMeta(title="Netzwerk-Scan")
                if path.endswith(".pdf"):
                    export_service.export_pdf(Path(path), md, "markdown", meta, logo_path=self.window_._logo_path())
                elif path.endswith(".html"):
                    export_service.export_html(Path(path), md, "markdown", meta,
                                               logo_data_uri=self.window_._logo_data_uri())
                else:
                    Path(path).write_text(md, encoding="utf-8")
            self.status.setText(f"Exportiert: {Path(path).name}")
        except OSError as error:
            self.status.setText(f"Export fehlgeschlagen: {error}")


def _ip_key(ip: str):
    try:
        import ipaddress
        return (0, int(ipaddress.ip_address(ip)))
    except ValueError:
        return (1, ip)


def _rows(devices, comments):
    for d in devices:
        yield [d.ip, d.name, d.mac, d.vendor, comments.get(d.key, ""), d.services(),
               str(d.rtt_ms) if d.rtt_ms is not None else ""]


def _export_csv(path, devices, comments) -> None:
    import csv
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["IP", "Name", "MAC", "Hersteller", "Kommentar", "Dienste", "ms"])
        writer.writerows(_rows(devices, comments))


def _export_json(path, devices, comments) -> None:
    import json
    data = [{"ip": d.ip, "name": d.name, "mac": d.mac, "vendor": d.vendor,
             "comment": comments.get(d.key, ""), "ports": d.ports, "rtt_ms": d.rtt_ms} for d in devices]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _export_markdown(devices, comments) -> str:
    lines = ["# Netzwerk-Scan", "", f"- Geräte: {len(devices)}", "",
             "| IP | Name | MAC | Hersteller | Kommentar | Dienste | ms |", "|---|---|---|---|---|---|---|"]
    for row in _rows(devices, comments):
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in row) + " |")
    return "\n".join(lines)
