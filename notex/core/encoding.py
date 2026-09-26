"""Textdateien lesen: Encoding und Zeilenenden erkennen, beim Speichern beibehalten.

Erkennung (in dieser Reihenfolge):
1. UTF-8 mit BOM  (die 3 Bytes EF BB BF am Anfang)     -> "utf-8-sig"
2. UTF-16 mit BOM (FF FE / FE FF)                     -> "utf-16"
3. UTF-8 ohne BOM (Bytes lassen sich strikt dekodieren) -> "utf-8"
4. Fallback cp1252 (Windows-Westeuropa)                -> "cp1252"
5. Sonst Latin-1 (jedes Byte gültig, z. B. Binärdateien)  -> "latin-1"

Intern arbeitet der Editor immer mit "\n". Beim Speichern werden die
Zeilenenden wieder in das Original-Format (CRLF oder LF) gewandelt.
"""
from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path

CRLF = "\r\n"
LF = "\n"


@dataclass
class TextFile:
    text: str        # Inhalt, Zeilenenden normalisiert auf "\n"
    encoding: str    # "utf-8-sig" | "utf-8" | "cp1252"
    eol: str         # "\r\n" oder "\n"


def detect_encoding(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16"      # z. B. CSV-Export aus Excel („Unicode-Text“)
    try:
        data.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    try:
        data.decode("cp1252")
        return "cp1252"
    except UnicodeDecodeError:
        return "latin-1"     # cp1252 kennt 0x81/0x8D/0x8F/0x90/0x9D nicht; Latin-1 dekodiert jedes Byte verlustfrei


def detect_eol(text: str) -> str:
    """CRLF, sobald mindestens ein \\r\\n vorkommt – sonst LF (auch bei leerer Datei)."""
    return CRLF if CRLF in text else LF


def decode_bytes(data: bytes) -> TextFile:
    encoding = detect_encoding(data)
    raw_text = data.decode(encoding)
    eol = detect_eol(raw_text)
    # Erst CRLF, dann einsame CR (alte Mac-Dateien) auf LF bringen
    text = raw_text.replace(CRLF, LF).replace("\r", LF)
    return TextFile(text=text, encoding=encoding, eol=eol)


def decode_as(data: bytes, encoding: str) -> TextFile:
    """Bytes mit einem vom Nutzer gewählten Encoding lesen (Erkennung überschreiben).

    Nicht dekodierbare Bytes werden zu U+FFFD statt eines Fehlers – der Nutzer sieht dann, dass die Wahl
    nicht passt, und kann eine andere probieren. utf-8-sig entfernt ein vorhandenes BOM.
    """
    if encoding == "utf-8" and data.startswith(codecs.BOM_UTF8):
        encoding = "utf-8-sig"
    raw_text = data.decode(encoding, errors="replace")
    eol = detect_eol(raw_text)
    return TextFile(text=raw_text.replace(CRLF, LF).replace("\r", LF), encoding=encoding, eol=eol)


def read_text_file(path: Path) -> TextFile:
    return decode_bytes(Path(path).read_bytes())


def encode_text(text: str, encoding: str, eol: str) -> bytes:
    """Wandelt Editor-Text zurück in Bytes – mit Original-Zeilenenden und -Encoding.

    cp1252 kann nicht jedes Zeichen darstellen (z. B. Emojis). Damit nichts
    stillschweigend verloren geht, werden solche Zeichen als XML-Referenz
    (&#128512;) geschrieben statt durch "?" ersetzt.
    """
    with_eol = text.replace(LF, eol) if eol != LF else text
    errors = "xmlcharrefreplace" if encoding in ("cp1252", "latin-1") else "strict"
    return with_eol.encode(encoding, errors=errors)
