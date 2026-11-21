# Quellpaket prüfen und installieren

Das Quellpaket enthält den Offline-Installer, Python-Quellen, Tests, Anleitungen und Showcase-Aufnahmen. Es braucht keinen Kompilierungsschritt. Python ≥ 3.11, GTK 4 und PyGObject werden vom System bereitgestellt. Die Installationsanleitung steht im [README](../README.md).

## Integrität und Tests

Prüfe zunächst das Archiv mit der mitgelieferten äußeren Prüfsumme. Entpacke es danach und prüfe den enthaltenen Dateisatz. Die innere Prüfsummenliste ist selbst durch die äußere Prüfsumme abgesichert.

```sh
sha256sum -c retronotes-0.2.0-rc1.tar.gz.sha256
tar -xzf retronotes-0.2.0-rc1.tar.gz
cd retronotes-0.2.0-rc1
sha256sum -c SHA256SUMS
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

`MANIFEST.txt` enthält alle Pfade des Pakets. `SHA256SUMS` enthält die SHA-256-Prüfsummen aller Paketdateien außer der Prüfsummenliste selbst. Führe die Tests in einer grafischen Linux-Sitzung aus, damit beide GTK-Fenstertests laufen.

## Archiv reproduzieren

Verwende GNU tar und gzip aus einem Verzeichnis, das den geprüften Paket-Root `retronotes-0.2.0-rc1` enthält. Das Manifest bestimmt den Inhalt, Dateimodi stammen aus dem Paket, Archivpfade, Reihenfolge, Zeitstempel und numerische Besitzer werden normalisiert. Installationsreste oder lokale Git-Daten fließen dadurch nicht ein.

```sh
cd retronotes-0.2.0-rc1
LC_ALL=C tar --format=ustar --mtime='@0' --owner=0 --group=0 --numeric-owner \
  --mode='u+rw,go+r,go-w' --no-recursion --transform='s,^,retronotes-0.2.0-rc1/,' \
  -cf - -T MANIFEST.txt | gzip -n -9 > ../retronotes-0.2.0-rc1.tar.gz
cd ..
sha256sum retronotes-0.2.0-rc1.tar.gz
```

## Manuelle Abnahme mit getrenntem Notizordner

1. Mit `review=$(mktemp -d)` ein Testverzeichnis anlegen und `python install.py --prefix "$review/app"` ausführen.
2. Mit `"$review/app/bin/rnote" --notes-dir "$review/notes"` starten. Eine Notiz anlegen, synthetischen Markdown-Text eingeben, auf `SAVED` warten und mit `Ctrl+W` schließen.
3. Mit derselben Befehlszeile erneut starten. Text prüfen, mit `Ctrl+P` nach dem Titel filtern und mit `Ctrl+F` einen Begriff in der Notiz suchen. Mit `F1` das FIELD MANUAL öffnen.
4. In einem Terminal `chmod 500 "$review/notes"` ausführen, im Editor eine Zeile ergänzen und den sichtbaren Speicherfehler sowie die Schließsperre prüfen. Mit `chmod 700 "$review/notes"` und `Ctrl+S` speichern und anschließend schließen.
5. Mit derselben Befehlszeile und zusätzlichem `--quick` starten. Eine zweite Testnotiz schreiben und mit `Ctrl+Enter` schließen. Beide Markdown-Dateien im Testordner kontrollieren.
6. Mit `python install.py --prefix "$review/app" --uninstall` deinstallieren. Beide Testnotizen müssen im Testordner erhalten bleiben.
