# RetroNotes 0.2.0 · Release Candidate

RetroNotes ist ein lokaler GTK-Notizblock für UTF-8-Markdown. Der erste Release-Kandidat bündelt den bestehenden Editor, Autosave, Notizindex und Suche in der aktuellen Notiz, Quick Entry sowie den Offline-Installer.

- Neue Notizen sind mit Modus `0600` privat. Neue Notizordner und Papierkörbe verwenden Modus `0700`.
- Der Notizindex ignoriert Symlinks. Lesen und Schreiben prüfen, dass die Zieldatei eine reguläre Markdown-Datei im gewählten Ordner ist.
- Autosave überprüft den Dateistand erneut unmittelbar vor dem atomaren Austausch. Bei erkannten Konflikten bleibt der Entwurf im Fenster.
- Ungültiges UTF-8 und NUL-Bytes werden beim Öffnen gemeldet. Ein bereits geöffneter Entwurf bleibt erhalten.
- Quick Entry zeigt Fehler beim Anlegen an. Der Offline-Installer prüft seine Zielpfade und ersetzt Programmdateien einzeln atomar.

Die Zielumgebung ist Linux mit GTK 4. Bedienung und bekannte Grenzen stehen im [README](../README.md) und im [FIELD MANUAL](FIELD_MANUAL.md). Die [Paketanleitung](PACKAGE.md) beschreibt Installations-, Prüf- und Reproduktionsschritte.
