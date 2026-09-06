# Medienmitteilungen veröffentlichen

Eine Medienmitteilung kommt auf die Website, indem sie in OpenCloud im Space
**WebSync** im Ordner **Medienmitteilungen** abgelegt wird. Der Abgleich holt sie
von dort ab und stellt sie unter «Geschichten» auf kinderkrippe-olten.ch. Er läuft
fest einmal pro Woche, am Montagmorgen; soll eine Mitteilung früher erscheinen,
kann ihn die Person, die die Website betreut, von Hand starten.

## Ordner anlegen

Pro Mitteilung ein Ordner, benannt nach diesem Muster:

    2026-09-04_Hort
    JJJJ-MM-TT_<Ort>[_<Thema>]

* **Datum** – erscheint auf der Website als Datum der Mitteilung.
* **Ort** – `Sonnhalde`, `Hagmatt`, `Hort` (= Bifang-Säli) oder `Verein`.
  Gross- und Kleinschreibung spielt keine Rolle, `Bifang-Säli` geht ebenso. Ein
  anderes Wort an dieser Stelle wird nicht erkannt, und dann wird der Ordner nicht
  verarbeitet.
* **Thema** – freiwillig, z. B. `2026-09-04_Hort_Eroeffnung`. Nötig nur, wenn am
  selben Tag zwei Mitteilungen zum selben Ort erscheinen.

**Erlaubte Zeichen:** zwischen den Unterstrichen nur Buchstaben, Ziffern und
Bindestriche. Umlaute sind in Ordnung – `2026-09-04_Bifang-Säli_Eroeffnung` ist
ein gültiger Name. Ein Leerzeichen, ein Punkt oder ein Apostroph dagegen nicht;
so ein Ordner wird nicht verarbeitet, und die Meldung dazu nennt genau diese
Regel. Der Ordnername wird zur Adresse der Seite, deshalb die enge Regel.

**Zwei Ordner, die sich nur in der Gross-/Kleinschreibung unterscheiden**
(`2026-09-04_hort` und `2026-09-04_Hort`), würden dieselbe Seite ergeben. Dann
wird *keiner* von beiden verarbeitet – die Meldung nennt jeweils den anderen
Ordner und bittet um eine Umbenennung. Einen der beiden umzubenennen genügt.

## In den Ordner gehören

* **Genau ein** Dokument: `.docx` oder `.pdf`.
  Beide ergeben Zwischentitel und einen fetten Lead-Absatz. Das `.docx` ist
  trotzdem die bessere Wahl: dort wird der Aufbau direkt übernommen, während er
  aus einem PDF anhand von Schrift und Abständen rekonstruiert werden muss – bei
  ungewöhnlichem Layout kann das abweichen.
* **Fotos** als einzelne Bilddateien (`.jpg`, `.jpeg`, `.png`), so viele wie
  gewünscht. Sie werden zur Bildergalerie am Ende der Seite, in der Reihenfolge
  der Dateinamen. Sehr kleine Bilder – kleiner als etwa 200 × 200 Pixel – werden
  für Logos gehalten und weggelassen. Bilder, die im Dokument stecken, kommen
  ebenfalls auf die Seite – bei einem PDF sind das die Fassungen aus dem PDF,
  meist stärker verkleinert als die Originale.
* Wahlweise eine `meta.yaml` (siehe unten).
* Sonst nichts. Eine fremde Datei, ein zweites Dokument oder ein Unterordner
  führt dazu, dass der Ordner nicht verarbeitet wird.

**Achtung bei Fotos vom iPhone:** iPhones speichern Fotos standardmässig im
Format `.heic`, und das gehört nicht zu den drei Bildformaten oben. Eine einzige
`.heic`-Datei im Ordner zählt als fremde Datei – dann wird der **ganze Ordner
nicht verarbeitet** und es erscheint gar nichts, auch die Mitteilung selbst
nicht. Die Fotos also vor dem Hochladen als JPEG speichern.

**Jede einzelne Datei darf höchstens 25 MB gross sein.** Grössere Dateien können
nicht aus OpenCloud abgeholt werden. Die Seite erscheint dann *ohne* diese Datei,
und der Abgleich wird als fehlerhaft gemeldet, mit dem Dateinamen dabei. Fotos
also vorher verkleinern – direkt aus der Kamera sind sie fast immer klein genug,
aus einer Bildbearbeitung nicht unbedingt.

## Aufbau des Dokuments

Die Website übernimmt die Struktur des Dokuments – aus dem `.docx` genauso wie
aus dem PDF:

| Im Dokument | Auf der Website |
|---|---|
| `MEDIENMITTEILUNG` zuoberst | wird weggelassen |
| erster Absatz (nach dem Label) | Titel der Seite |
| fetter Absatz direkt darunter | Lead, bleibt fett |
| jeder weitere ganz fette Absatz | Zwischentitel |
| eingebettetes Bild | Titelbild der Seite |
| `Bildlegende: …` | Bildunterschrift zum Titelbild |
| Absatz mit einer Zeile, die mit einer Postleitzahl beginnt | wird ganz weggelassen |

Lead und Zwischentitel werden an der **Fettschrift** erkannt, nicht an den
Word-Formatvorlagen. Für den Titel bitte keine Formatvorlage «Überschrift 1»
verwenden – aus einem `.docx` erscheint sonst ein «#» im Titel der Seite. Ein
ganz normaler, fett formatierter Absatz ist genau richtig.

Die Adresse wird an der Postleitzahl erkannt und **absichtlich entfernt** – auf
der Website steht sie ohnehin schon. Das gilt aber nicht nur für den Adressblock
am Schluss: Beginnt *irgendwo* im Dokument eine Zeile mit einer vierstelligen
Postleitzahl und einem Ortsnamen («4600 Olten»), so verschwindet der **ganze
Absatz**, in dem diese Zeile steht – mitsamt allem anderen, was in diesem Absatz
steht.

Soll eine Adresse stehen bleiben, etwa ein Veranstaltungsort, dann so schreiben,
dass keine Zeile mit der Postleitzahl beginnt. «Die Feier findet im Stadthaus,
4600 Olten, statt» mitten im Fliesstext bleibt erhalten; eine eigene Zeile
«4600 Olten» nimmt ihren Absatz mit.

Ist das Bild im Dokument dasselbe wie eines der losen Fotos, wird es **nicht
doppelt** angezeigt. Es genügt also, das Foto ganz normal ins Dokument
einzufügen und zusätzlich beizulegen; als Titelbild wird automatisch die
schärfere der beiden Fassungen genommen.

Steckt im Dokument gar kein Bild, erscheint auf der Seite selbst auch kein
Titelbild – für die Kachel auf der Startseite wird dann das erste der losen
Fotos verwendet, und eine `Bildlegende:` bleibt ungenutzt.

## `meta.yaml` – für Kurztitel, Autorin und Ort

Der Titel einer Medienmitteilung ist oft lang, die Kachel auf der Startseite ist
schmal. Für einen kürzeren Kacheltitel eine Datei `meta.yaml` in den Ordner
legen:

```yaml
TeaserTitle: Eröffnung Hort
Autor: Melanie von Arx
Site: Hort
```

Alle Angaben sind freiwillig:

* `TeaserTitle` – der Titel auf der Kachel. Ohne diese Angabe steht dort der
  volle Titel.
* `Autor` – wer die Mitteilung verfasst hat. Ohne Angabe wird der Name aus den
  Dokumenteigenschaften übernommen. Er wird in der Seite festgehalten, zurzeit
  aber nirgends angezeigt.
* `Site` – überschreibt den Ort aus dem Ordnernamen, für den Fall, dass eine
  Mitteilung zu einem anderen Ort gehört, als der Ordnername sagt. Es gelten
  dieselben Schreibweisen wie dort: `Sonnhalde`, `Hagmatt`, `Hort` (oder
  `Bifang-Säli`) und `Verein`. Steht hier etwas anderes – `Site: Kita` etwa –,
  wird der ganze Ordner nicht verarbeitet und die Mitteilung erscheint gar nicht.

Die Datei muss genau `meta.yaml` heissen, alles klein geschrieben. `meta.yml`
gilt als fremde Datei, und dann wird der ganze Ordner abgewiesen; `Meta.yaml`
wird stillschweigend übergangen.

Die Schlüsselwörter genau so schreiben, jeweils am Zeilenanfang und ohne
Einrückung. Ein Tippfehler im *Schlüsselwort* – `Teasertitle:` statt
`TeaserTitle:` – kostet nur diese eine Angabe: die Mitteilung erscheint
trotzdem, einfach ohne Kurztitel, und der Bericht des Abgleichs hält fest,
welches Schlüsselwort übergangen wurde. Für die *Werte* gilt das nicht: eine
Schreibweise bei `Site:`, die nicht in der Liste oben steht, kostet nicht bloss
diese Zeile, sondern die ganze Mitteilung.

**Wichtig:** `meta.yaml` ist der *einzige* Ort, an dem diese Angaben dauerhaft
bestehen bleiben. Die Seite wird bei jeder Änderung neu erzeugt – was direkt auf
der Website geändert wird, geht dabei verloren.

## Ändern und Zurückziehen

* **Ändern** – Dokument oder Fotos in OpenCloud ersetzen. Die Seite wird neu
  erzeugt.
* **Zurückziehen** – den Ordner in OpenCloud löschen. Die Seite verschwindet von
  der Website. Sie bleibt in der Versionsgeschichte erhalten und lässt sich
  wiederherstellen.
* **Die allerletzte verbliebene Mitteilung** entfernt der Abgleich nicht von
  selbst: Sähe er nach einer Störung plötzlich gar keine Ordner mehr, würde er
  sonst alles löschen, und genau davor schützt diese Sperre. Diese eine Seite
  muss deshalb die Person entfernen, die die Website betreut – sie startet den
  Abgleich dazu von Hand und setzt dabei zusätzlich das Häkchen «Permit removing
  the last remaining page» (`allow_empty`). Ein gewöhnlicher Lauf von Hand
  genügt dafür nicht.

## Wenn eine Mitteilung nicht erscheint

Ein Ordner, der nicht verarbeitet werden kann, wird **nicht angerührt**: Es wird
nichts erzeugt, nichts geändert und vor allem nichts gelöscht. War die
Mitteilung schon einmal veröffentlicht, bleibt die Seite genau so stehen, wie
sie ist. Es geht also nichts verloren, solange der Fehler behoben wird.

Die häufigsten Gründe:

* Der Ordnername passt nicht ins Muster oder enthält ein nicht erlaubtes
  Zeichen.
* Der `<Ort>` im Ordnernamen ist keiner der erlaubten – oder `Site:` in der
  `meta.yaml` ist es nicht.
* Zwei Ordner unterscheiden sich nur in der Gross-/Kleinschreibung.
* Es liegt kein Dokument im Ordner – oder es liegen zwei darin. Auch eine
  temporäre Word-Datei (`~$Name.docx`, die entsteht, solange das Dokument
  geöffnet ist) zählt als zweites Dokument.
* Eine fremde Datei oder ein Unterordner liegt im Ordner – eine `.heic`-Datei
  vom iPhone ist der häufigste Fall.
* Aus dem Dokument liess sich kein Text lesen: es ist leer, oder es steht nichts
  darin ausser dem Wort `MEDIENMITTEILUNG`. Dasselbe gilt, wenn sich die Datei
  gar nicht öffnen lässt – etwa weil ein altes `.doc` einfach in `.docx`
  umbenannt wurde.
* Eine Datei ist grösser als 25 MB. Dann fehlt sie auf der Seite, und der
  Abgleich meldet das als Fehler; ist es das Dokument selbst, gilt der Ordner
  als «ohne Dokument» und wird abgewiesen.
* Es gibt auf der Website schon einen gleichnamigen Beitrag, der nicht aus
  OpenCloud stammt – die älteren, von Hand erstellten Geschichten. Diese werden
  nie überschrieben; ein anderes `<Thema>` im Ordnernamen löst das.

**Wann der Abgleich läuft:** fest einmal pro Woche, am Montagmorgen. Zusätzlich
kann ihn die Person, die die Website betreut, jederzeit von Hand starten. Eine
Mitteilung, die noch nicht auf der Website steht, ist also nicht zwingend
abgewiesen worden – vielleicht wartet sie einfach auf den nächsten Lauf. Wer
nicht bis Montag warten will, fragt dort nach.

Was schiefgelaufen ist, steht im Protokoll des Abgleichs. Die Meldungen dort sind
auf **Englisch** und nennen jeweils den Ordnernamen; nach deutschem Text muss man
also nicht suchen. Wer nicht weiterkommt, wendet sich an die Person, die die
Website betreut.

Dateien, die direkt im Ordner `Medienmitteilungen` liegen und nicht in einem der
Mitteilungs-Ordner, werden übergangen. Dort darf also liegen, was für die
Autorinnen nützlich ist – verarbeitet werden nur die Ordner.
