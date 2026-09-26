"""Dateityp-Erkennung über Magic Bytes – eigene kleine Signatur-Tabelle, keine libmagic-Abhängigkeit. Ohne Qt.

detect(head, name) liest nur die ersten Bytes (HEAD_BYTES) und liefert einen FileType. ZIP-basierte Formate
(docx/xlsx/pptx/odt/jar/apk/epub) werden über ihre typischen Einträge am Anfang des Archivs bzw. die Endung
erkannt. looks_binary() entscheidet, ob eine Datei mit unbekanntem Inhalt als Hex statt als Text geöffnet wird.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

HEAD_BYTES = 8192


@dataclass(frozen=True)
class FileType:
    key: str                  # "png", "zip", "text" …
    name: str                 # Anzeige: „PNG-Bild“
    extensions: tuple[str, ...]
    category: str             # image | document | archive | executable | database | encrypted | text | binary

    @property
    def label(self) -> str:
        return self.name


def _t(key, name, exts, category):
    return FileType(key, name, tuple(exts), category)


PNG = _t("png", "PNG-Bild", [".png"], "image")
JPEG = _t("jpeg", "JPEG-Bild", [".jpg", ".jpeg", ".jfif"], "image")
GIF = _t("gif", "GIF-Bild", [".gif"], "image")
WEBP = _t("webp", "WebP-Bild", [".webp"], "image")
BMP = _t("bmp", "BMP-Bild", [".bmp"], "image")
ICO = _t("ico", "Windows-Icon", [".ico"], "image")
TIFF = _t("tiff", "TIFF-Bild", [".tif", ".tiff"], "image")
PDF = _t("pdf", "PDF-Dokument", [".pdf"], "document")
ZIP = _t("zip", "ZIP-Archiv", [".zip"], "archive")
DOCX = _t("docx", "Word-Dokument (ZIP-basiert)", [".docx", ".docm", ".dotx"], "document")
XLSX = _t("xlsx", "Excel-Tabelle (ZIP-basiert)", [".xlsx", ".xlsm", ".xltx"], "document")
PPTX = _t("pptx", "PowerPoint (ZIP-basiert)", [".pptx", ".pptm"], "document")
ODF = _t("odf", "OpenDocument (ZIP-basiert)", [".odt", ".ods", ".odp"], "document")
EPUB = _t("epub", "E-Book (ZIP-basiert)", [".epub"], "document")
JAR = _t("jar", "Java-Archiv (ZIP-basiert)", [".jar", ".war"], "archive")
APK = _t("apk", "Android-Paket (ZIP-basiert)", [".apk", ".aab"], "archive")
RAR = _t("rar", "RAR-Archiv", [".rar"], "archive")
SEVENZ = _t("7z", "7-Zip-Archiv", [".7z"], "archive")
GZIP = _t("gzip", "GZIP-Archiv", [".gz", ".tgz"], "archive")
BZIP2 = _t("bzip2", "BZIP2-Archiv", [".bz2", ".tbz2"], "archive")
XZ = _t("xz", "XZ-Archiv", [".xz", ".txz"], "archive")
ELF = _t("elf", "ELF-Programm (Linux)", ["", ".so", ".o", ".elf"], "executable")
PE = _t("pe", "Windows-Programm (PE/EXE)", [".exe", ".dll", ".sys", ".scr", ".cpl", ".ocx", ".efi"], "executable")
MACHO = _t("macho", "Mach-O-Programm (macOS)", ["", ".dylib"], "executable")
SQLITE = _t("sqlite", "SQLite-Datenbank", [".sqlite", ".sqlite3", ".db", ".db3"], "database")
NTX = _t("ntx", "Verschlüsselte Notex-Notiz", [".ntx"], "encrypted")
CLASS = _t("class", "Java-Klasse", [".class"], "executable")
WASM = _t("wasm", "WebAssembly", [".wasm"], "executable")
MP3 = _t("mp3", "MP3-Audio", [".mp3"], "media")
OGG = _t("ogg", "Ogg-Medien", [".ogg", ".oga", ".ogv", ".opus"], "media")
FLAC = _t("flac", "FLAC-Audio", [".flac"], "media")
WAV = _t("wav", "WAV-Audio", [".wav"], "media")
MP4 = _t("mp4", "MP4/MOV-Video", [".mp4", ".m4a", ".m4v", ".mov"], "media")
TAR = _t("tar", "TAR-Archiv", [".tar"], "archive")
PCAP = _t("pcap", "Netzwerk-Mitschnitt (PCAP)", [".pcap", ".cap", ".dmp"], "capture")
PCAPNG = _t("pcapng", "Netzwerk-Mitschnitt (PCAPNG)", [".pcapng", ".ntar"], "capture")
EVTX = _t("evtx", "Windows-Ereignisprotokoll (EVTX)", [".evtx"], "log")
TEXT = _t("text", "Text", [], "text")
BINARY = _t("binary", "Binärdaten (unbekannt)", [], "binary")
EMPTY = _t("empty", "Leere Datei", [], "text")

# (Offset, Bytes, Typ) – die Reihenfolge zählt: spezifische Signaturen zuerst
SIGNATURES: list[tuple[int, bytes, FileType]] = [
    (0, b"NOTEXENC", NTX),
    (0, b"ElfFile\x00", EVTX),
    (0, b"\xd4\xc3\xb2\xa1", PCAP), (0, b"\xa1\xb2\xc3\xd4", PCAP),      # Mikrosekunden, LE/BE
    (0, b"\x4d\x3c\xb2\xa1", PCAP), (0, b"\xa1\xb2\x3c\x4d", PCAP),      # Nanosekunden, LE/BE
    (0, b"\x0a\x0d\x0d\x0a", PCAPNG),
    (257, b"ustar", TAR),
    (0, b"\x89PNG\r\n\x1a\n", PNG),
    (0, b"\xff\xd8\xff", JPEG),
    (0, b"GIF87a", GIF),
    (0, b"GIF89a", GIF),
    (0, b"%PDF-", PDF),
    (0, b"Rar!\x1a\x07", RAR),
    (0, b"7z\xbc\xaf\x27\x1c", SEVENZ),
    (0, b"\x1f\x8b", GZIP),
    (0, b"BZh", BZIP2),
    (0, b"\xfd7zXZ\x00", XZ),
    (0, b"\x7fELF", ELF),
    (0, b"SQLite format 3\x00", SQLITE),
    (0, b"\xfe\xed\xfa\xce", MACHO), (0, b"\xfe\xed\xfa\xcf", MACHO),
    (0, b"\xce\xfa\xed\xfe", MACHO), (0, b"\xcf\xfa\xed\xfe", MACHO),
    (0, b"\xca\xfe\xba\xbe", CLASS),      # auch Mach-O-Universal; Java ist häufiger
    (0, b"\x00asm", WASM),
    (0, b"BM", BMP),
    (0, b"\x00\x00\x01\x00", ICO),
    (0, b"II*\x00", TIFF), (0, b"MM\x00*", TIFF),
    (0, b"ID3", MP3),
    (0, b"OggS", OGG),
    (0, b"fLaC", FLAC),
    (0, b"PK\x03\x04", ZIP), (0, b"PK\x05\x06", ZIP), (0, b"PK\x07\x08", ZIP),
]

_ZIP_REFINE = {
    ".docx": DOCX, ".docm": DOCX, ".dotx": DOCX, ".xlsx": XLSX, ".xlsm": XLSX, ".xltx": XLSX,
    ".pptx": PPTX, ".pptm": PPTX, ".odt": ODF, ".ods": ODF, ".odp": ODF, ".epub": EPUB,
    ".jar": JAR, ".war": JAR, ".apk": APK, ".aab": APK,
}


def looks_binary(head: bytes) -> bool:
    """Nullbytes oder viele Steuerzeichen ⇒ binär. UTF-16 mit BOM gilt als Text."""
    if not head:
        return False
    if head.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return False
    if b"\x00" in head:
        return True
    control = sum(1 for b in head if b < 32 and b not in (9, 10, 12, 13, 27))
    return control / len(head) > 0.10


def _refine_zip(head: bytes, suffix: str) -> FileType:
    if suffix in _ZIP_REFINE:
        return _ZIP_REFINE[suffix]
    if b"[Content_Types].xml" in head:
        if b"word/" in head:
            return DOCX
        if b"xl/" in head:
            return XLSX
        if b"ppt/" in head:
            return PPTX
        return DOCX
    if b"mimetypeapplication/epub+zip" in head:
        return EPUB
    if b"mimetypeapplication/vnd.oasis.opendocument" in head:
        return ODF
    if b"AndroidManifest.xml" in head or b"classes.dex" in head:
        return APK
    if b"META-INF/MANIFEST.MF" in head:
        return JAR
    return ZIP


def detect(head: bytes, name: str = "") -> FileType:
    """Typ aus den ersten Bytes; `name` hilft nur bei ZIP-Varianten."""
    suffix = Path(name).suffix.lower()
    if not head:
        return EMPTY
    for offset, magic, ftype in SIGNATURES:
        if head[offset:offset + len(magic)] == magic:
            if ftype is ZIP:
                return _refine_zip(head, suffix)
            if ftype is CLASS and suffix not in (".class",) and head[4:8] < b"\x00\x00\x00\x2d":
                return MACHO             # Mach-O-Universal: kleine Architekturanzahl statt Java-Version
            return ftype
    if head.startswith(b"MZ") and len(head) >= 64:
        pe_offset = int.from_bytes(head[60:64], "little")
        if pe_offset + 4 <= len(head) and head[pe_offset:pe_offset + 4] == b"PE\x00\x00":
            return PE
        return PE if suffix in PE.extensions else BINARY
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return WAV
    if head[4:8] == b"ftyp":
        return MP4
    return BINARY if looks_binary(head) else TEXT


def detect_file(path: Path) -> FileType:
    try:
        with open(path, "rb") as handle:
            return detect(handle.read(HEAD_BYTES), path.name)
    except OSError:
        return BINARY


# Endungen, bei denen Text der erwartete Inhalt ist (kein Widerspruch bei TEXT)
TEXTUAL_SUFFIXES = {".txt", ".md", ".markdown", ".log", ".csv", ".tsv", ".json", ".yaml", ".yml", ".ini", ".cfg",
                    ".toml", ".xml", ".html", ".htm", ".css", ".js", ".ts", ".py", ".sh", ".ps1", ".bat", ".cmd",
                    ".sql", ".svg", ".c", ".h", ".cpp", ".java", ".cs", ".go", ".rs", ".rb", ".php", ".conf", ".env"}


def mismatch(name: str, ftype: FileType) -> str | None:
    """Warntext, wenn Endung und Inhalt nicht zusammenpassen – sonst None."""
    suffix = Path(name).suffix.lower()
    if ftype.key in ("binary", "empty"):
        return None
    if ftype.key == "text":
        if suffix and suffix not in TEXTUAL_SUFFIXES and any(suffix in t.extensions for _o, _m, t in SIGNATURES):
            return f"Endung {suffix} erwartet Binärdaten, der Inhalt ist aber Text"
        return None
    if not suffix and ftype.key in ("elf", "macho"):
        return None
    if suffix in ftype.extensions:
        return None
    if ftype.key == "zip" and suffix in _ZIP_REFINE:
        return None
    return f"Inhalt ist {ftype.name}, passt nicht zur Endung {suffix or '(keine)'}"
