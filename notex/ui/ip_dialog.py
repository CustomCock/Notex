"""IP-Übersicht: alle IP-Zuordnungen aus den Notizen, nach Subnetz gruppiert, Konflikte rot, Doppelklick springt
zur Stelle; Subnetz-Auswertung (belegt/frei, Ausschlussbereiche, nächste freie IP kopieren)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from notex.core import fileops, ipmap
from notex.theme.icons import icon
from notex.theme.tokens import COLORS, SPACING


class IpOverviewDialog(QDialog):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.window_ = window
        self.cfg = window.config.setdefault("ip_conflicts", {})
        self.setWindowTitle("IP-Übersicht")
        self.resize(900, 640)
        self.tree = QTreeWidget()
        self.tree.setObjectName("AnalysisTree")
        self.tree.setHeaderLabels(["IP", "Host", "Fundstelle"])
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 220)
        self.tree.itemDoubleClicked.connect(self._jump)
        self.tree.currentItemChanged.connect(self._select_subnet)
        self.network = QLineEdit(self.cfg.get("network", ""))
        self.network.setPlaceholderText("Subnetz, z. B. 10.0.0.0/24")
        self.exclusions = QLineEdit(self.cfg.get("exclusions", ""))
        self.exclusions.setPlaceholderText("Ausschließen, z. B. 10.0.0.100-10.0.0.199 (DHCP), 10.0.0.1")
        self.result = QLabel()
        self.result.setObjectName("SettingsNote")
        self.copy_button = QPushButton("Nächste freie IP kopieren")
        self.copy_button.clicked.connect(self._copy_next)
        self.copy_button.setEnabled(False)
        subnet_row = QHBoxLayout()
        subnet_row.addWidget(self.network, 1)
        subnet_row.addWidget(self.exclusions, 2)
        subnet_row.addWidget(self.copy_button)
        self.status = QLabel()
        self.status.setObjectName("SettingsNote")
        refresh = QPushButton("Aktualisieren")
        refresh.clicked.connect(lambda: self.window_.refresh_ip_index(full=True))
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        footer = QHBoxLayout()
        footer.addWidget(self.status, 1)
        footer.addWidget(refresh)
        footer.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACING.lg, SPACING.lg, SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)
        layout.addWidget(self.tree, 1)
        layout.addLayout(subnet_row)
        layout.addWidget(self.result)
        layout.addLayout(footer)
        self.network.textChanged.connect(self._evaluate)
        self.exclusions.textChanged.connect(self._evaluate)
        self.assignments: list[ipmap.Assignment] = []
        self._next: str | None = None

    def show_assignments(self, assignments: list[ipmap.Assignment]) -> None:
        self.assignments = assignments
        conflicts = ipmap.conflicts(assignments)
        red = QColor(COLORS.danger)
        warn = icon("triangle-alert", COLORS.danger)
        root = self.window_.root
        expanded = {self.tree.topLevelItem(i).text(0).split(" ")[0] for i in range(self.tree.topLevelItemCount())
                    if self.tree.topLevelItem(i).isExpanded()}
        self.tree.clear()
        for subnet, items in ipmap.group(assignments).items():
            bad = sum(1 for a in items if a.ip in conflicts)
            head = QTreeWidgetItem([f"{subnet}  ·  {len(items)} Einträge" + (f"  ·  {bad} im Konflikt" if bad else "")])
            head.setData(0, Qt.ItemDataRole.UserRole, subnet)
            if bad:
                head.setForeground(0, red)
                head.setIcon(0, warn)
            for item in items:
                where = item.file.relative_to(root) if fileops.is_within(item.file, root) else item.file
                child = QTreeWidgetItem([item.ip, item.host, f"{where}:{item.line + 1}"])
                child.setData(0, Qt.ItemDataRole.UserRole, item)
                if item.ip in conflicts:
                    child.setIcon(0, warn)          # Farbe allein reicht nicht (Stylesheet, Farbsehschwäche)
                    others = [f"{o.host} ({o.file.name}:{o.line + 1})" for o in conflicts[item.ip] if o != item]
                    for column in range(3):
                        child.setForeground(column, red)
                        child.setToolTip(column, "Konflikt – dieselbe IP auch bei: " + ", ".join(others))
                head.addChild(child)
            self.tree.addTopLevelItem(head)
            head.setFirstColumnSpanned(True)
            head.setExpanded(subnet in expanded or bool(bad) or len(assignments) < 60)
        self.status.setText(f"{len(assignments)} Zuordnung(en) · {len(conflicts)} Konflikt(e) · Quelle: .md/.txt in "
                            "data/ (ohne verschlüsselte Notizen)")
        self._evaluate()

    def _select_subnet(self, current, _previous) -> None:
        if current is None:
            return
        data = current.data(0, Qt.ItemDataRole.UserRole)
        subnet = data if isinstance(data, str) else ipmap.subnet_of(data.ip) if data else ""
        if subnet and not self.network.hasFocus():
            self.network.setText(subnet)

    def _evaluate(self) -> None:
        self.cfg["network"], self.cfg["exclusions"] = self.network.text(), self.exclusions.text()
        self._next = None
        self.copy_button.setEnabled(False)
        if not self.network.text().strip():
            self.result.setText("Subnetz eingeben oder eine Gruppe wählen, um belegte und freie Adressen zu sehen.")
            return
        try:
            use = ipmap.usage(self.network.text(), self.assignments, self.exclusions.text())
        except ValueError as error:
            self.result.setText(f"Eingabe nicht lesbar: {error}")
            return
        self._next = use.next_free
        self.copy_button.setEnabled(use.next_free is not None)
        text = f"{use.network}: {use.total} nutzbare Adressen · belegt {len(use.used)} · ausgeschlossen " \
               f"{use.excluded} · frei {use.free}"
        self.result.setText(text + (f" · nächste freie: {use.next_free}" if use.next_free else " · keine frei"))

    def _copy_next(self) -> None:
        if self._next:
            QGuiApplication.clipboard().setText(self._next)
            self.status.setText(f"{self._next} kopiert")

    def _jump(self, item, _column) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, ipmap.Assignment):
            self.window_.tabs.open_file(data.file, line=data.line + 1)
