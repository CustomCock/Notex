"""Textoperationen für die Bearbeitungsleiste – reine Funktionen auf Strings, ohne Qt.

Zeilenoperationen arbeiten auf einer Liste von Zeilen (ohne Zeilenenden),
Markdown-Toggles auf der Auswahl bzw. auf ganzen Zeilen.
"""
from __future__ import annotations

import re
from datetime import datetime

LIST_MARKER = re.compile(r"^(\s*)([-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)")
HEADING = re.compile(r"^(#{1,6})\s+")


# ---- Zeilen ------------------------------------------------------------------------
def duplicate_lines(lines: list[str]) -> list[str]:
    return lines + lines


def move_lines(lines: list[str], start: int, end: int, direction: int) -> tuple[list[str], int, int]:
    """Verschiebt lines[start:end] um eine Zeile nach oben (-1) oder unten (+1).
    Gibt (neue Zeilen, neuer Start, neues Ende) zurück; am Rand passiert nichts."""
    if direction < 0 and start == 0 or direction > 0 and end >= len(lines):
        return lines, start, end
    block = lines[start:end]
    rest_before, rest_after = lines[:start], lines[end:]
    if direction < 0:
        moved = rest_before[:-1] + block + [rest_before[-1]] + rest_after
        return moved, start - 1, end - 1
    moved = rest_before + [rest_after[0]] + block + rest_after[1:]
    return moved, start + 1, end + 1


def sort_lines(lines: list[str]) -> list[str]:
    return sorted(lines, key=lambda line: line.casefold())


def unique_lines(lines: list[str]) -> list[str]:
    """Entfernt doppelte Zeilen, behält die erste Fundstelle und die Reihenfolge."""
    seen: set[str] = set()
    result = []
    for line in lines:
        if line not in seen:
            seen.add(line)
            result.append(line)
    return result


def strip_trailing_whitespace(lines: list[str]) -> list[str]:
    return [line.rstrip(" \t") for line in lines]


# ---- Text ---------------------------------------------------------------------------
def to_upper(text: str) -> str:
    return text.upper()


def to_lower(text: str) -> str:
    return text.lower()


def to_title(text: str) -> str:
    """Wortanfänge groß, Rest unverändert (kein str.title(): das macht "don't" zu "Don'T")."""
    return re.sub(r"(^|(?<=\s))(\S)", lambda m: m.group(1) + m.group(2).upper(), text)


def date_time_stamp(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%d.%m.%Y %H:%M")


# ---- Markdown -----------------------------------------------------------------------
def toggle_wrap(text: str, marker: str, end_marker: str | None = None) -> str:
    """Umschließt `text` mit marker…end_marker oder entfernt die Umschließung wieder."""
    end_marker = marker if end_marker is None else end_marker
    if text.startswith(marker) and text.endswith(end_marker) and len(text) >= len(marker) + len(end_marker):
        return text[len(marker):len(text) - len(end_marker)]
    return f"{marker}{text}{end_marker}"


def toggle_bold(text: str) -> str:
    return toggle_wrap(text or "Fett", "**")


def toggle_italic(text: str) -> str:
    return toggle_wrap(text or "Kursiv", "*")


def toggle_code(text: str) -> str:
    if "\n" in text:
        return toggle_wrap(text, "```\n", "\n```")
    return toggle_wrap(text or "code", "`")


def toggle_link(text: str, url: str = "https://") -> str:
    match = re.fullmatch(r"\[([^\]]*)\]\([^)]*\)", text)
    if match:
        return match.group(1)
    return f"[{text or 'Linktext'}]({url})"


def toggle_heading(line: str, level: int = 2) -> str:
    """Setzt eine Überschrift der Stufe `level`; hat die Zeile schon diese Stufe, wird sie entfernt."""
    match = HEADING.match(line)
    if match:
        rest = line[match.end():]
        return rest if len(match.group(1)) == level else f"{'#' * level} {rest}"
    return f"{'#' * level} {line}"


def toggle_list(lines: list[str]) -> list[str]:
    """Macht aus Zeilen Listenpunkte ("- ") oder nimmt die Punkte wieder weg (wenn alle welche haben)."""
    all_listed = all(LIST_MARKER.match(line) for line in lines if line.strip())
    result = []
    for line in lines:
        match = LIST_MARKER.match(line)
        if all_listed and match:
            result.append(match.group(1) + line[match.end():])
        elif not all_listed and line.strip():
            indent = len(line) - len(line.lstrip())
            result.append(line[:indent] + "- " + line[indent:])
        else:
            result.append(line)
    return result


def toggle_checkbox(lines: list[str]) -> list[str]:
    """Fügt "- [ ] " ein; vorhandene Checkboxen werden umgeschaltet ([ ] <-> [x])."""
    result = []
    for line in lines:
        if not line.strip():
            result.append(line)
            continue
        match = re.match(r"^(\s*[-*+]\s+)\[( |x|X)\]\s+", line)
        if match:
            state = "x" if match.group(2) == " " else " "
            result.append(f"{match.group(1)}[{state}] " + line[match.end():])
        else:
            list_match = re.match(r"^(\s*)([-*+]\s+)", line)
            if list_match:
                result.append(list_match.group(1) + list_match.group(2) + "[ ] " + line[list_match.end():])
            else:
                indent = len(line) - len(line.lstrip())
                result.append(line[:indent] + "- [ ] " + line[indent:])
    return result


# ---- Hängende Einrückung ---------------------------------------------------------------
def hanging_prefix(line: str) -> str:
    """Der Teil am Zeilenanfang, den umgebrochene Folgezeilen übernehmen: Einrückung + Listenmarker."""
    match = LIST_MARKER.match(line)
    if match:
        return match.group(0)
    return line[:len(line) - len(line.lstrip(" \t"))]
