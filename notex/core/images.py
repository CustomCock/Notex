"""Bilder in Notizen: Einfügen als Datei in assets/ neben der Notiz, Links, Aufräumen. Ohne Qt.

- Einfügen (Zwischenablage/Drag & Drop) nur in Markdown-Notizen und NIE in .ntx: das Bild läge sonst
  unverschlüsselt neben der verschlüsselten Notiz (can_embed_images).
- assets/ liegt im Ordner der Notiz; der Ordnername ist einstellbar. Dateiname: Notizname + Zeitstempel.
- Links sind relativ zur Notiz und URL-kodiert (Leerzeichen → %20), damit Vorschau und andere Programme sie lesen.
- Verschiebt man eine Notiz in einen anderen Ordner, können die Bilder mitwandern (plan_assets_move).
- Unbenutzte Bilder werden nur gefunden, nie automatisch gelöscht (find_unused_images).
"""
from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath

from notex.core.fileops import is_encrypted_path

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
NOTE_SUFFIXES = (".md", ".markdown", ".txt")
DEFAULT_ASSETS = "assets"
_IMAGE_LINK = re.compile(r"!\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))(?:\s+\"[^\"]*\")?\s*\)")
_HTML_IMG = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)


def is_image(path: Path | str) -> bool:
    return str(path).lower().endswith(IMAGE_SUFFIXES)


def can_embed_images(note: Path | str) -> bool:
    """Bilder einfügen nur in Markdown – und nie in verschlüsselte Notizen (.ntx-Regel)."""
    if is_encrypted_path(note):
        return False
    return str(note).lower().endswith((".md", ".markdown"))


def safe_stem(name: str) -> str:
    stem = re.sub(r"[^\w.-]+", "-", name, flags=re.UNICODE).strip("-.")
    return stem[:60] or "bild"


def asset_name(note: Path, now: datetime, suffix: str = ".png", existing: set[str] | None = None) -> str:
    """„notiz-20260926-143005.png“, bei Kollision „…-2.png“."""
    base = f"{safe_stem(note.stem)}-{now:%Y%m%d-%H%M%S}"
    existing = existing or set()
    name, n = f"{base}{suffix}", 2
    while name.lower() in existing:
        name = f"{base}-{n}{suffix}"
        n += 1
    return name


def assets_dir(note: Path, folder_name: str = DEFAULT_ASSETS) -> Path:
    folder_name = folder_name.strip().strip("/\\") or DEFAULT_ASSETS
    if ".." in Path(folder_name).parts:
        folder_name = DEFAULT_ASSETS
    return note.parent / folder_name


def relative_link(note: Path, image: Path) -> str:
    rel = os.path.relpath(image, note.parent).replace(os.sep, "/")
    return urllib.parse.quote(rel, safe="/._-~")


def markdown_image(note: Path, image: Path, alt: str = "") -> str:
    return f"![{alt}]({relative_link(note, image)})"


def image_links(text: str) -> list[str]:
    """Alle Bildziele einer Notiz (Markdown und <img>), dekodiert, ohne externe URLs."""
    out = []
    for m in list(_IMAGE_LINK.finditer(text)) + list(_HTML_IMG.finditer(text)):
        target = next(g for g in m.groups() if g).strip()
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):   # http:, data:, file: …
            continue
        out.append(urllib.parse.unquote(target.split("#")[0].split("?")[0]))
    return out


def resolve_link(note: Path, target: str) -> Path:
    return Path(os.path.normpath(note.parent / Path(*PurePosixPath(target).parts)))


@dataclass
class AssetMove:
    """Plan für das Mitnehmen der Bilder einer Notiz beim Verschieben in einen anderen Ordner."""
    moves: list[tuple[Path, Path]] = field(default_factory=list)   # (alt, neu) – verschieben
    copies: list[tuple[Path, Path]] = field(default_factory=list)  # (alt, neu) – kopieren, weil andere Notizen sie nutzen
    new_text: str = ""

    @property
    def empty(self) -> bool:
        return not self.moves and not self.copies


def plan_assets_move(old_note: Path, new_note: Path, text: str, other_texts: dict[Path, str],
                     folder_name: str = DEFAULT_ASSETS) -> AssetMove:
    """Bilder aus dem assets-Ordner neben der alten Notiz, die diese Notiz verlinkt, in den assets-Ordner
    neben der neuen Notiz einplanen und die Links umschreiben. Bilder, die andere Notizen im alten Ordner
    ebenfalls verwenden, werden kopiert statt verschoben. Nur sinnvoll, wenn sich der Ordner ändert."""
    plan = AssetMove(new_text=text)
    if old_note.parent == new_note.parent:
        return plan
    old_assets, new_assets = assets_dir(old_note, folder_name), assets_dir(new_note, folder_name)
    used_elsewhere: set[Path] = set()
    for other, other_text in other_texts.items():
        if other == old_note:
            continue
        for target in image_links(other_text):
            used_elsewhere.add(resolve_link(other, target))
    seen: set[Path] = set()
    replacements: dict[str, str] = {}
    for m in _IMAGE_LINK.finditer(text):
        raw = (m.group(1) or m.group(2)).strip()
        target = urllib.parse.unquote(raw.split("#")[0].split("?")[0])
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
            continue
        source = resolve_link(old_note, target)
        try:
            source.relative_to(old_assets)
        except ValueError:
            continue    # nur Bilder aus dem eigenen assets-Ordner wandern mit
        destination = new_assets / source.relative_to(old_assets)
        if source not in seen:
            seen.add(source)
            (plan.copies if source in used_elsewhere else plan.moves).append((source, destination))
        replacements[raw] = relative_link(new_note, destination)
    new_text = text
    for raw, new in replacements.items():
        new_text = new_text.replace(f"](<{raw}>)", f"]({new})").replace(f"]({raw})", f"]({new})")
    plan.new_text = new_text
    return plan


def find_unused_images(root: Path, texts: dict[Path, str]) -> list[Path]:
    """Bilder unter root, auf die keine der gegebenen Notizen verweist (Markdown-Bild, <img> oder Wiki-Link [[bild.png]]).
    Verschlüsselte Notizen können nicht geprüft werden – der Aufrufer weist darauf hin."""
    used: set[Path] = set()
    names_linked: set[str] = set()
    for note, text in texts.items():
        for target in image_links(text):
            used.add(resolve_link(note, target))
        for m in re.finditer(r"\[\[([^\]|#]+)", text):
            names_linked.add(Path(m.group(1).strip()).name.lower())
        for m in re.finditer(r"\]\(\s*<?([^)\s>]+)>?\s*\)", text):   # auch normale Links auf Bilder zählen
            target = urllib.parse.unquote(m.group(1))
            if not re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                used.add(resolve_link(note, target))
    unused = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if is_image(name) and path not in used and name.lower() not in names_linked:
                unused.append(path)
    return unused
