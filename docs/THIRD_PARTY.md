# Lizenz und Abhängigkeiten

RetroNotes steht unter der [MIT-Lizenz](../LICENSE). K3RN hat die Rechte für den Release einschließlich der Beiträge aus der RetroTools-Familie bestätigt.

| Komponente | Verwendung | Lizenz |
| --- | --- | --- |
| Python ≥ 3.11 | Interpreter und Standardbibliothek des Systems | [PSF und enthaltene Hinweise](https://docs.python.org/3/license.html) |
| GTK 4 und PyGObject ≥ 3.42 | Native Oberfläche und Python-Bindings des Systems | [GTK LGPL](https://github.com/GNOME/gtk/blob/main/README.md), [PyGObject LGPL-2.1-or-later](https://pygobject.gnome.org/) |
| Setuptools ≥ 68 | Build-Backend für Python-Paketwerkzeuge | [MIT](https://github.com/pypa/setuptools/blob/main/LICENSE) |

Diese Abhängigkeiten werden über das System oder Python-Paketwerkzeuge bezogen. Das Quellpaket enthält keine Kopien ihrer Distributionen. Die Showcase-Aufnahmen zeigen die echte GTK-Anwendung mit eigens erstellten synthetischen Notizen. Die Palette für die Aufnahmen wurde nur dem Testprozess bereitgestellt. Die verwendete Desktop-Monospace-Schrift erscheint gerendert in den Aufnahmen. Eine Schriftdatei ist kein Paketbestandteil.

## Herkunft innerhalb der RetroTools

| Projekt | Verwendung in RetroNotes |
| --- | --- |
| RetroView | GTK-Familienbasis für die native Oberfläche |
| RetroControl | Referenz für Omarchy-Palettenpfade und semantische Farbrollen |

Die beiden Projekte dienen als Grundlage beziehungsweise Referenz. Als Laufzeitabhängigkeiten genügen die oben genannten Systemkomponenten.
