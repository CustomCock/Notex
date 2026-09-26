# Lizenzen der gebündelten Drittkomponenten

Notex selbst steht unter der MIT-Lizenz (siehe LICENSE). Die portable App bündelt
folgende Komponenten. Die vollständigen Lizenztexte liegen an den genannten Orten
und werden mit in den Build-Ordner kopiert (`_internal/notex/assets/...`,
`_internal/notex/dictionaries/...`, `licenses/`).

| Komponente | Version | Lizenz | Quelle | Lizenztext |
|---|---|---|---|---|
| Python | 3.12 | PSF License | https://www.python.org | `licenses/LICENSE-Python.txt` |
| PySide6 / Qt for Python | 6.11.2 | LGPL v3 (dynamisch gelinkt, austauschbar im Ordner `_internal`) | https://www.qt.io/qt-for-python | `licenses/LICENSE-PySide6-LGPLv3.txt` |
| Qt | 6.11 | LGPL v3 | https://www.qt.io | wie PySide6 |
| pyenchant | 3.3.0 | LGPL v2.1+ | https://github.com/pyenchant/pyenchant | `licenses/LICENSE-pyenchant.txt` |
| Enchant + Hunspell (im Windows-Wheel von pyenchant) | 2.x / 1.7 | LGPL v2.1+ / LGPL-GPL-MPL (Tri-Lizenz) | https://abiword.github.io/enchant/ · https://hunspell.github.io | `licenses/LICENSE-pyenchant.txt` |
| spylls | 0.1.7 | MPL 2.0 | https://github.com/zverok/spylls | `licenses/LICENSE-spylls.txt` |
| Send2Trash | 2.1.0 | BSD 3-Clause | https://github.com/arsenetar/send2trash | `licenses/LICENSE-send2trash.txt` |
| Pygments | 2.x | BSD 2-Clause | https://pygments.org | `licenses/LICENSE-Pygments.txt` |
| markdown-it-py | 3.x/4.x | MIT | https://github.com/executablebooks/markdown-it-py | `licenses/LICENSE-markdown-it-py.txt` |
| mdurl | 0.1.x | MIT | https://github.com/executablebooks/mdurl | `licenses/LICENSE-mdurl.txt` |
| regex (mrab-regex) | 2024+ | Apache License 2.0 (Teile CNRI-Python) | https://github.com/mrabarnett/mrab-regex | `licenses/LICENSE-regex.txt` |
| PyYAML | 6.0.3 | MIT License | https://pyyaml.org | `licenses/LICENSE-PyYAML.txt` |
| cryptography (pyca) | 44–51 | Apache License 2.0 oder BSD 3-Clause (wahlweise) | https://cryptography.io | `licenses/LICENSE-cryptography.txt` |
| OpenSSL (in cryptography enthalten) | 3.x | Apache License 2.0 | https://www.openssl.org | `licenses/LICENSE-cryptography.txt` (Apache-Text) |
| cffi | 1.x/2.x | MIT | https://cffi.readthedocs.io | `licenses/LICENSE-cffi.txt` |
| pycparser | 2.x/3.x | BSD 3-Clause | https://github.com/eliben/pycparser | `licenses/LICENSE-pycparser.txt` |
| Inter (Schrift) | 4.1 | SIL Open Font License 1.1 | https://rsms.me/inter | `notex/assets/fonts/LICENSE-Inter.txt` |
| JetBrains Mono (Schrift) | 2.304 | SIL Open Font License 1.1 | https://www.jetbrains.com/lp/mono | `notex/assets/fonts/LICENSE-JetBrainsMono.txt` |
| Lucide Icons | 2026 | ISC | https://lucide.dev | `notex/assets/icons/LICENSE-Lucide.txt` |
| Hunspell-Wörterbuch de_DE (frami, igerman98) | LibreOffice dictionaries | GPL v2 oder v3 | https://github.com/LibreOffice/dictionaries · https://www.j3e.de/ispell/igerman98 | `notex/dictionaries/LICENSE_de_DE_GPLv2.txt`, `README_de_DE.txt` |
| Hunspell-Wörterbuch en_US (SCOWL) | 2020.12.07 | MIT/BSD-artig (SCOWL, Ispell, WordNet) | http://wordlist.sourceforge.net | `notex/dictionaries/README_en_US_LICENSE.txt` |

## Einordnung

- **MIT für Notex** ist mit allen Komponenten verträglich. LGPL-Bibliotheken (Qt, PySide6,
  pyenchant/Enchant) werden nur benutzt, nicht verändert, und liegen als eigenständige Dateien
  im Ordner `_internal`, sodass sie austauschbar sind – das ist die Bedingung der LGPL für
  proprietär oder MIT lizenzierte Anwendungen.
- Das **deutsche Wörterbuch** ist GPL-lizenziert. Es ist ein Datenwerk, das Notex nur einliest;
  es wird nicht in den Code eingebaut. Die Auslieferung nebeneinander im selben ZIP ist eine
  „bloße Aggregation“ im Sinne der GPL und verpflichtet Notex nicht zur GPL. Der GPL-Text und
  die Herkunft liegen bei. Wer Notex weiterverteilt, muss das Wörterbuch weiterhin unter GPL
  weitergeben (oder weglassen).
- **PyInstaller** (GPL v2 mit Ausnahme) ist nur Build-Werkzeug; sein Bootloader darf mit
  beliebig lizenzierten Programmen ausgeliefert werden.
- **SF Pro** wird nie mitgeliefert (Apple-Lizenz). Eigene Schriften in `fonts/user/` liegen in
  der Verantwortung des Nutzers.
- **LanguageTool** wird nicht gebündelt, sondern optional über HTTP angesprochen.
