import os
import zlib
from pathlib import Path

import pytest

from notex.core import entropy as en


def test_shannon_extremes() -> None:
    assert en.shannon(b"") == 0.0
    assert en.shannon(b"\x00" * 1000) == 0.0
    assert en.shannon(bytes(range(256)) * 4) == pytest.approx(8.0)
    assert en.shannon(b"ab" * 100) == pytest.approx(1.0)


def test_auto_block_size() -> None:
    assert en.auto_block_size(1000) == 1024
    assert en.auto_block_size(2000 * 5000) == 16384
    assert en.auto_block_size(10 * 1024 ** 3) >= 4 * 1024 * 1024


def test_profile_regions_and_assessment(tmp_path: Path) -> None:
    text = ("Das ist ganz normaler deutscher Text mit Wörtern und Sätzen. " * 800).encode("utf-8")
    random_part = os.urandom(64 * 1024)
    padding = b"\x00" * (32 * 1024)
    path = tmp_path / "mix.bin"
    path.write_bytes(text + random_part + padding)
    prof = en.profile(path, 4096)
    assert len(prof.values) == -(-path.stat().st_size // 4096)
    kinds = [kind for _s, _e, kind in en.regions(prof)]
    assert "high" in kinds and "low" in kinds
    high = next((s, e) for s, e, k in en.regions(prof) if k == "high")
    assert abs(high[0] - len(text)) <= 4096 and abs(high[1] - (len(text) + len(random_part))) <= 4096
    assert "Gemischt" in en.assess(prof)


# Daten erst im Test erzeugen: große Parameter würden als Test-ID in PYTEST_CURRENT_TEST landen
# (unter Windows höchstens 32 767 Zeichen je Umgebungsvariable)
SAMPLES = {
    "zufall": (lambda: os.urandom(256 * 1024), "Komprimiert oder verschlüsselt"),
    "zlib": (lambda: zlib.compress(os.urandom(64 * 1024) * 3), "Komprimiert oder verschlüsselt"),
    "text": (lambda: ("Einfacher Text. " * 20000).encode(), "Text oder einfach strukturierte Daten"),
    "nullen": (lambda: b"\x00" * 100000, "Fast leer oder gleichförmig"),
}


@pytest.mark.parametrize("name", list(SAMPLES))
def test_assessment(tmp_path: Path, name: str) -> None:
    make, expected = SAMPLES[name]
    path = tmp_path / "x.bin"
    path.write_bytes(make())
    assert en.assess(en.profile(path)).startswith(expected)


def test_small_blocks_of_random_data_reach_high() -> None:
    from collections import Counter
    data = os.urandom(1024)
    assert en._block_entropy(Counter(data), len(data)) >= en.HIGH          # dank Korrektur
    text = b"Normaler Text mit Leerzeichen und Satzzeichen. " * 22
    assert en._block_entropy(Counter(text[:1024]), 1024) < 5.0


def test_total_matches_whole_file(tmp_path: Path) -> None:
    data = os.urandom(10_000) + b"A" * 50_000
    path = tmp_path / "t.bin"
    path.write_bytes(data)
    assert en.profile(path, 1024).total == pytest.approx(en.shannon(data))


def test_empty_cancel_progress(tmp_path: Path) -> None:
    empty = tmp_path / "leer.bin"
    empty.write_bytes(b"")
    prof = en.profile(empty)
    assert prof.values == [] and en.assess(prof) == "Leere Datei"
    path = tmp_path / "p.bin"
    path.write_bytes(os.urandom(100_000))
    seen = []
    en.profile(path, 1024, progress=lambda d, t: seen.append((d, t)))
    assert seen[-1] == (100_000, 100_000)
    with pytest.raises(en.Cancelled):
        en.profile(path, cancelled=lambda: True)
    assert en.format_value(7.456) == "7,46"
