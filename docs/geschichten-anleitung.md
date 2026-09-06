# Geschichten veröffentlichen

Eine Geschichte aus dem Kita-Alltag kommt auf die Website, indem sie in OpenCloud
im Space **WebSync** im Ordner **Geschichten** abgelegt wird. Der Abgleich holt
sie von dort ab und stellt sie unter «Geschichten» auf kinderkrippe-olten.ch. Er
läuft fest einmal pro Woche, am Montagmorgen; soll eine Geschichte früher
erscheinen, kann ihn die Person, die die Website betreut, von Hand starten.

Der Abgleich ist derselbe wie für die Medienmitteilungen – nur eben für einen
anderen Ordner in OpenCloud. Wer schon Medienmitteilungen ablegt, kennt alles,
was hier steht; die beiden Anleitungen unterscheiden sich fast nur im Ordner.

## Ordner anlegen

Pro Geschichte ein Ordner, benannt nach diesem Muster:

    2026-06-25_Hagmatt_Bauernhof
    JJJJ-MM-TT_<Ort>[_<Thema>]

* **Datum** – erscheint auf der Website als Datum der Geschichte.
* **Ort** – `Sonnhalde`, `Hagmatt`, `Hort` (= Bifang-Säli) oder `Verein`.
  Gross- und Kleinschreibung spielt keine Rolle, `Bifang-Säli` geht ebenso. Ein
  anderes Wort an dieser Stelle wird nicht erkannt, und dann wird der Ordner nicht
  verarbeitet.
* **Thema** – freiwillig, z. B. `2026-06-25_Hagmatt_Bauernhof`. Nötig nur, wenn am
  selben Tag zwei Geschichten zum selben Ort erscheinen – und praktisch, um eine
  Geschichte auf einen Blick wiederzuerkennen.

**Erlaubte Zeichen:** zwischen den Unterstrichen nur Buchstaben, Ziffern und
Bindestriche. Umlaute sind in Ordnung – `2026-06-25_Bifang-Säli_Sommerfest` ist
ein gültiger Name. Ein Leerzeichen, ein Punkt oder ein Apostroph dagegen nicht;
so ein Ordner wird nicht verarbeitet, und die Meldung dazu nennt genau diese
Regel. Der Ordnername wird zur Adresse der Seite, deshalb die enge Regel.

**Zwei Ordner, die sich nur in der Gross-/Kleinschreibung unterscheiden**
(`2026-06-25_hagmatt` und `2026-06-25_Hagmatt`), würden dieselbe Seite ergeben.
Dann wird *keiner* von beiden verarbeitet – die Meldung nennt jeweils den anderen
Ordner und bittet um eine Umbenennung. Einen der beiden umzubenennen genügt.

## In den Ordner gehören

* **Genau ein** Dokument, am besten ein `.docx`. Es enthält den Text der
  Geschichte. (Ein `.pdf` wird ebenfalls verarbeitet, ist hier aber die
  schlechtere Wahl: der Aufbau muss dann anhand von Schrift und Abständen
  rekonstruiert werden.)
* **Fotos** als einzelne Bilddateien (`.jpg`, `.jpeg`, `.png`), so viele wie
  gewünscht. Sie werden zur Bildergalerie – dem Schieber am Ende der Seite –, in
  der Reihenfolge der Dateinamen. Sehr kleine Bilder – kleiner als etwa
  200 × 200 Pixel – werden für Logos gehalten und weggelassen.
* Wahlweise ein **Titelbild** unter dem Namen `teaser.jpg` (oder `teaser.png`):
  siehe unten.
* Wahlweise eine `meta.yaml` (siehe unten).
* Sonst nichts. Eine fremde Datei, ein zweites Dokument oder ein Unterordner
  führt dazu, dass der Ordner nicht verarbeitet wird.

**Achtung bei Fotos vom iPhone:** iPhones speichern Fotos standardmässig im
Format `.heic`, und das gehört nicht zu den drei Bildformaten oben. Eine einzige
`.heic`-Datei im Ordner zählt als fremde Datei – dann wird der **ganze Ordner
nicht verarbeitet** und es erscheint gar nichts, auch der Text nicht. Die Fotos
also vor dem Hochladen als JPEG speichern.

**Achtung bei geöffneten Word-Dateien:** solange ein Dokument in Word offen ist,
liegt daneben eine temporäre Datei `~$Name.docx`. Die zählt als zweites Dokument.
Vor dem Hochladen also Word schliessen.

**Jede einzelne Datei darf höchstens 25 MB gross sein.** Grössere Dateien können
nicht aus OpenCloud abgeholt werden. Die Seite erscheint dann *ohne* diese Datei,
und der Abgleich wird als fehlerhaft gemeldet, mit dem Dateinamen dabei. Fotos
also vorher verkleinern – direkt aus der Kamera sind sie fast immer klein genug,
aus einer Bildbearbeitung nicht unbedingt.

## Aufbau des Dokuments

Die Website übernimmt die Struktur des Dokuments:

| Im Dokument | Auf der Website |
|---|---|
| erster Absatz | Titel der Seite |
| fetter Absatz direkt darunter | Lead, bleibt fett |
| jeder weitere ganz fette Absatz | Zwischentitel |
| eingebettetes Bild | Titelbild der Seite (sofern kein `teaser.jpg` beiliegt) |
| `Bildlegende: …` | Bildunterschrift zum Titelbild |
| Absatz mit einer Zeile, die wie Postleitzahl und Ort aussieht | wird ganz weggelassen |

Zwischentitel werden an der **Fettschrift** erkannt, nicht an den
Word-Formatvorlagen. Für den Titel bitte keine Formatvorlage «Überschrift 1»
verwenden – es erscheint sonst ein «#» im Titel der Seite. Ein ganz normaler
Absatz zuoberst ist genau richtig.

Alles Übrige bleibt so stehen, wie es geschrieben wurde. Eine Zeile wie «Text und
Fotos: Antonella Zbinden» am Schluss erscheint also genau dort – das ist der Weg,
einen Namen auf der Seite sichtbar zu machen (siehe `Autor` unten).

**Adressen:** Steht *irgendwo* im Dokument eine Zeile, die wie eine vierstellige
Postleitzahl mit Ortsnamen aussieht («4600 Olten»), so verschwindet der **ganze
Absatz**, in dem diese Zeile steht. Das ist für Medienmitteilungen gedacht, deren
Adressblock nicht auf die Seite gehört, gilt aber hier genauso. Entscheidend ist,
was nach den vier Ziffern kommt: folgen nur ein bis vier grossgeschriebene
Wörter, gilt die Zeile als Adresse. Ein einziges kleingeschriebenes Wort genügt,
damit sie stehen bleibt – «1990 Wurde der Verein gegründet» bleibt also erhalten.
Soll eine Adresse stehen bleiben, etwa ein Veranstaltungsort, dann einfach in
einen Satz einbauen: «Die Feier findet im Stadthaus, 4600 Olten, statt.»

## Titelbild selbst bestimmen: `teaser.jpg`

Von sich aus nimmt der Abgleich das Bild aus dem Dokument als Titelbild, und wenn
das Dokument keines enthält, das erste Foto nach Dateinamen. Bei einer Geschichte
mit vielen Fotos ist das selten das schönste.

Wer selbst bestimmen will, welches Foto oben auf der Seite und auf der Kachel
erscheint, legt eine **Kopie** dieses Fotos zusätzlich unter dem Namen
`teaser.jpg` (oder `teaser.png`) in den Ordner. Dieser Name gewinnt gegen alles
andere. Das Original behält dabei seinen Platz in der Galerie – die Kopie ersetzt
es also nicht, sie bestimmt nur, welches Foto oben steht.

## `meta.yaml` – für Kurztitel, Autorin, Ort und Gruppe

Der Titel einer Geschichte ist oft lang, die Kachel auf der Startseite ist
schmal. Für einen kürzeren Kacheltitel – und für die Gruppe – eine Datei
`meta.yaml` in den Ordner legen:

```yaml
TeaserTitle: Projekt Bauernhof
Autor: Antonella Zbinden
Site: Hagmatt
Group: fisch
```

Alle Angaben sind freiwillig:

* `TeaserTitle` – der Titel auf der Kachel. Ohne diese Angabe steht dort der
  volle Titel.
* `Autor` – wer die Geschichte verfasst hat. Ohne diese Angabe steht in der Seite
  gar kein Autor; aus den Dokumenteigenschaften wird **nichts** übernommen. Dort
  steht das Konto, das die Datei zuletzt gespeichert hat – oft der Name einer
  Stelle und nicht der Person, die geschrieben hat. Der Eintrag wird in der Seite
  festgehalten, zurzeit aber nirgends angezeigt. Soll ein Name auf der Seite
  sichtbar sein, gehört er als Zeile ins Dokument selbst («Text und Fotos: …»).
* `Site` – überschreibt den Ort aus dem Ordnernamen, für den Fall, dass eine
  Geschichte zu einem anderen Ort gehört, als der Ordnername sagt. Es gelten
  dieselben Schreibweisen wie dort: `Sonnhalde`, `Hagmatt`, `Hort` (oder
  `Bifang-Säli`) und `Verein`. Steht hier etwas anderes – `Site: Kita` etwa –,
  wird der ganze Ordner nicht verarbeitet und die Geschichte erscheint gar nicht.
* `Group` – die Gruppe, zu der die Geschichte gehört: in der Sonnhalde `papagei`,
  `balu` oder `regenbogen`, in der Hagmatt `fisch` oder `frosch`. Ohne diese
  Angabe gehört die Geschichte zum Ort als Ganzem. Erlaubt sind nur die Gruppen
  **dieses** Orts: `Group: fisch` auf einer Sonnhalde-Seite wird nicht
  verarbeitet, und beim Hort und beim Verein, die gar keine Gruppen haben, wird
  jede Angabe abgewiesen. Steht in derselben `meta.yaml` auch ein `Site:`, so
  zählen die Gruppen des dort genannten Orts.

Die Datei muss genau `meta.yaml` heissen, alles klein geschrieben. `meta.yml`
gilt als fremde Datei, und dann wird der ganze Ordner abgewiesen; `Meta.yaml`
wird stillschweigend übergangen.

Die Schlüsselwörter genau so schreiben, jeweils am Zeilenanfang und ohne
Einrückung. Ein Tippfehler im *Schlüsselwort* – `Teasertitle:` statt
`TeaserTitle:` – kostet nur diese eine Angabe: die Geschichte erscheint trotzdem,
einfach ohne Kurztitel, und der Bericht des Abgleichs hält fest, welches
Schlüsselwort übergangen wurde. Für die *Werte* gilt das nicht: eine Schreibweise
bei `Site:` oder `Group:`, die nicht in der Liste oben steht, kostet nicht bloss
diese Zeile, sondern die ganze Geschichte.

**Wichtig:** `meta.yaml` ist der *einzige* Ort, an dem diese Angaben dauerhaft
bestehen bleiben. Die Seite wird bei jeder Änderung neu erzeugt – was direkt auf
der Website geändert wird, geht dabei verloren.

## Ändern und Zurückziehen

* **Ändern** – Dokument oder Fotos in OpenCloud ersetzen. Die Seite wird neu
  erzeugt.
* **Zurückziehen** – den Ordner in OpenCloud löschen. Die Seite verschwindet von
  der Website. Sie bleibt in der Versionsgeschichte erhalten und lässt sich
  wiederherstellen.
* **Die allerletzte verbliebene Geschichte aus OpenCloud** entfernt der Abgleich
  nicht von selbst: Sähe er nach einer Störung plötzlich gar keine Ordner mehr,
  würde er sonst alles löschen, und genau davor schützt diese Sperre. Diese eine
  Seite muss deshalb die Person entfernen, die die Website betreut – sie startet
  den Abgleich dazu von Hand und setzt dabei zusätzlich das Häkchen «Permit
  removing the last remaining page» (`allow_empty`).

**Die älteren Geschichten auf der Website sind davon nicht betroffen.** Der
Abgleich rührt nur Seiten an, die er selbst aus dem Ordner `Geschichten` erzeugt
hat. Von Hand erstellte Beiträge und die Seiten aus dem Ordner
`Medienmitteilungen` bleiben unangetastet – auch dann, wenn in OpenCloud gar
nichts liegt.

## Wenn eine Geschichte nicht erscheint

Ein Ordner, der nicht verarbeitet werden kann, wird **nicht angerührt**: Es wird
nichts erzeugt, nichts geändert und vor allem nichts gelöscht. War die Geschichte
schon einmal veröffentlicht, bleibt die Seite genau so stehen, wie sie ist. Es
geht also nichts verloren, solange der Fehler behoben wird.

Die häufigsten Gründe:

* Der Ordnername passt nicht ins Muster oder enthält ein nicht erlaubtes Zeichen.
* Der `<Ort>` im Ordnernamen ist keiner der erlaubten – oder `Site:` bzw.
  `Group:` in der `meta.yaml` ist es nicht.
* Zwei Ordner unterscheiden sich nur in der Gross-/Kleinschreibung.
* Es liegt kein Dokument im Ordner – oder es liegen zwei darin (auch eine
  temporäre `~$Name.docx` zählt).
* Eine fremde Datei oder ein Unterordner liegt im Ordner – eine `.heic`-Datei vom
  iPhone ist der häufigste Fall.
* Aus dem Dokument liess sich kein Text lesen: es ist leer, oder die Datei lässt
  sich gar nicht öffnen – etwa weil ein altes `.doc` einfach in `.docx` umbenannt
  wurde.
* Eine Datei ist grösser als 25 MB. Dann fehlt sie auf der Seite, und der
  Abgleich meldet das als Fehler; ist es das Dokument selbst, gilt der Ordner als
  «ohne Dokument» und wird abgewiesen.
* Es gibt auf der Website schon einen gleichnamigen Beitrag, der nicht aus diesem
  Ordner stammt – etwa eine ältere, von Hand erstellte Geschichte. Diese werden
  nie überschrieben; ein anderes `<Thema>` im Ordnernamen löst das.

**Wann der Abgleich läuft:** fest einmal pro Woche, am Montagmorgen. Zusätzlich
kann ihn die Person, die die Website betreut, jederzeit von Hand starten. Eine
Geschichte, die noch nicht auf der Website steht, ist also nicht zwingend
abgewiesen worden – vielleicht wartet sie einfach auf den nächsten Lauf.

Was schiefgelaufen ist, steht im Protokoll des Abgleichs. Die Meldungen dort sind
auf **Englisch** und nennen jeweils den Ordnernamen; nach deutschem Text muss man
also nicht suchen. Wer nicht weiterkommt, wendet sich an die Person, die die
Website betreut.

Dateien, die direkt im Ordner `Geschichten` liegen und nicht in einem der
Geschichten-Ordner, werden übergangen. Dort darf also liegen, was für die
Autorinnen nützlich ist – verarbeitet werden nur die Ordner.
