"""Export nach PDF und HTML (Qt-Teil).

HTML: das fertige Dokument aus `core.export` wird einfach geschrieben.
PDF:  der Inhalts-Körper wird mit einem QTextDocument gesetzt und über QPdfWriter seitenweise gemalt;
      Kopf- (Logo + Titel + Meta) und Fußzeile (Fußtext + „Seite X von Y") malt ein QPainter je Seite.

Nichts hier liest verschlüsselte Dateien – die Oberfläche übergibt bereits entschlüsselten Text.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, Qt, QUrl
from PySide6.QtGui import QFont, QPainter, QPageLayout, QPageSize, QPdfWriter, QPixmap, QTextDocument
from PySide6.QtWidgets import QMessageBox

from notex.core import export
from notex.ui.diagram_image import svg_to_image

# Für Qt-Rich-Text (QTextDocument) taugliches CSS – ohne flex/@page, dafür die Inhalts-Stile.
QT_CSS = """
body { font-family: 'Inter', sans-serif; color: #1f2328; font-size: 11pt; }
h1 { font-size: 17pt; color: #1a1f24; }
h2 { font-size: 14pt; color: #1a1f24; }
h3 { font-size: 12pt; color: #1a1f24; }
pre { background: #f4f5f7; border: 1px solid #e0e3e8; padding: 8px;
      font-family: 'JetBrains Mono', monospace; font-size: 10pt; }
code { font-family: 'JetBrains Mono', monospace; }
table { border-collapse: collapse; }
th, td { border: 1px solid #cfd4da; padding: 4px 8px; }
th { background: #eef1f4; }
blockquote { color: #4a5360; }
a { color: #3f5876; }
"""


def export_html(out_path: Path, content: str, kind: str, meta: export.ExportMeta,
                name: str = "", base_dir: str = "", values: dict[str, str] | None = None,
                prefix: str = "§", logo_data_uri: str = "") -> None:
    meta.logo_data_uri = logo_data_uri or meta.logo_data_uri
    html = export.to_html_document(content, kind, meta, name=name, base_dir=base_dir, values=values, prefix=prefix)
    Path(out_path).write_text(html, encoding="utf-8")


def export_pdf(out_path: Path, content: str, kind: str, meta: export.ExportMeta,
               name: str = "", base_dir: str = "", values: dict[str, str] | None = None,
               prefix: str = "§", logo_path: Path | None = None) -> None:
    body, diagrams = export.body_parts(content, kind, name=name, base_dir=base_dir, values=values, prefix=prefix)

    writer = QPdfWriter(str(out_path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(16, 16, 16, 16), QPageLayout.Unit.Millimeter)
    writer.setTitle(meta.title)
    if meta.author:
        writer.setCreator(meta.author)
    resolution = writer.resolution()
    full = writer.pageLayout().paintRectPixels(resolution)   # Fläche innerhalb der Ränder, in Gerätepixeln
    width = full.width()

    header_h = int(resolution * 0.62)      # ~1,6 cm Kopf
    footer_h = int(resolution * 0.34)      # ~0,9 cm Fuß
    body_top = header_h
    body_h = full.height() - header_h - footer_h
    if body_h < 100:
        body_h = full.height()             # Notnagel bei winzigen Seiten

    # QTextDocument rechnet in logischen 96-dpi-Pixeln; der PDF-Maler in Geräte-dpi (meist 1200).
    # Deshalb den Inhalt in seinem eigenen 96-dpi-System setzen und den Maler beim Zeichnen skalieren.
    logical = 96.0
    factor = resolution / logical
    doc_w = width / factor
    doc_h = body_h / factor

    doc = QTextDocument()
    doc.setDefaultStyleSheet(QT_CSS)
    base_font = QFont("Inter")
    base_font.setPointSize(11)
    doc.setDefaultFont(base_font)
    for key, diagram in diagrams.items():           # Mermaid-Diagramme als hochaufgelöste Bilder (3× für den Druck)
        doc.addResource(QTextDocument.ResourceType.ImageResource.value, QUrl(f"notex-mermaid:{key}"),
                        svg_to_image(diagram.svg, diagram.width, diagram.height, 3.0, "#ffffff"))
    doc.setHtml(body)
    doc.setPageSize(QRectF(0, 0, doc_w, doc_h).size())
    page_count = max(1, doc.pageCount())

    logo = QPixmap(str(logo_path)) if logo_path and Path(logo_path).exists() else QPixmap()

    painter = QPainter(writer)
    try:
        for page in range(page_count):
            if page > 0:
                writer.newPage()
            _paint_header(painter, width, header_h, meta, logo, resolution)
            _paint_footer(painter, width, full.height(), footer_h, meta, page + 1, page_count, resolution)
            painter.save()
            painter.translate(0, body_top)                 # Kopfhöhe in Gerätepixeln
            painter.scale(factor, factor)                  # ab hier logische 96-dpi-Einheiten
            painter.setClipRect(QRectF(0, 0, doc_w, doc_h))
            painter.translate(0, -page * doc_h)
            doc.drawContents(painter)
            painter.restore()
    finally:
        painter.end()


def _paint_header(painter: QPainter, width: int, height: int, meta: export.ExportMeta,
                  logo: QPixmap, resolution: int) -> None:
    painter.save()
    x = 0
    if not logo.isNull():
        size = int(height * 0.62)
        scaled = logo.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(0, int((height - scaled.height()) / 2), scaled)
        x = scaled.width() + int(resolution * 0.12)
    title_font = QFont("Inter")
    title_font.setPointSize(15)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(Qt.GlobalColor.black)
    painter.drawText(QRectF(x, 0, width - x, height * 0.62), Qt.AlignmentFlag.AlignVCenter, meta.title)
    meta_font = QFont("Inter")
    meta_font.setPointSize(9)
    painter.setFont(meta_font)
    painter.setPen(Qt.GlobalColor.darkGray)
    bits = [meta.date_or_today()]
    if meta.author:
        bits.insert(0, meta.author)
    painter.drawText(QRectF(x, height * 0.60, width - x, height * 0.4),
                     Qt.AlignmentFlag.AlignVCenter, "  ·  ".join(bits))
    pen_y = int(height - resolution * 0.06)
    painter.setPen(Qt.GlobalColor.gray)
    painter.drawLine(0, pen_y, width, pen_y)
    painter.restore()


def _paint_footer(painter: QPainter, width: int, page_height: int, height: int,
                  meta: export.ExportMeta, page: int, pages: int, resolution: int) -> None:
    painter.save()
    top = page_height - height
    painter.setPen(Qt.GlobalColor.lightGray)
    painter.drawLine(0, int(top), width, int(top))
    foot_font = QFont("Inter")
    foot_font.setPointSize(8)
    painter.setFont(foot_font)
    painter.setPen(Qt.GlobalColor.gray)
    painter.drawText(QRectF(0, top, width, height), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                     meta.footer)
    painter.drawText(QRectF(0, top, width, height), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                     f"Seite {page} von {pages}")
    painter.restore()


def warn(parent, message: str) -> None:
    QMessageBox.warning(parent, "Export", message)
