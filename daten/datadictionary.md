# Datenwörterbuch

Quelle, Spalten, Typen, Bereinigungsregeln – und die Fallen, die im Export stecken.

## Ausgabeformat (verbindlich)

Alle Exporte für Power BI werden in **deutscher Schreibweise** geschrieben
(Festlegung Chris, 20.10.2026, bestätigt 03.11.2026):

| Merkmal | Wert |
| --- | --- |
| Trennzeichen | Semikolon `;` |
| Dezimaltrenner | Komma (z. B. `40,46`) |
| Kodierung | UTF-8 **mit** BOM |
| Datum | ISO `JJJJ-MM-TT` |
| Tausendertrennzeichen | keines |

**Warum:** Ein deutsches Power BI liest den **Punkt** als Tausendertrennzeichen.
Aus `40.46` wird dann still **4046** – Faktor 100. Der Fehler ist im Import nicht
sichtbar (kein Fehler, nur falsche Zahlen). Deshalb gilt: deutsch, immer.

Ausnahmen: In der **XLSX** stehen Zahlen als echte Zahlzellen – dort regelt
Excel die Anzeige. Die CSV-Dateien in `daten/` folgen der Regel oben.

## Quelle

| Quelle | Format | Inhalt | Zeitraum |
| --- | --- | --- | --- |
| Airbnb-Einnahmen-Export | CSV (UTF-8 BOM) | Buchungen, Payouts, Anpassungen | Jun 2020 – Nov 2026 |
| Airbnb-Monatsdateien | CSV | Teilmengen (10–12/2025, 05–08/2026) | Teilmenge |

**Entscheidungen:**
- Die **Gesamtdatei** ist die Quelle der Wahrheit. Die Monatsdateien sind reine
  Teilmengen mit inkonsistentem Spaltensatz (`Servicegebühr` fehlt bei
  05–07/2026, September 2026 fehlt ganz).
- `__MACOSX/._*`-Dateien werden verworfen (macOS-Metadaten).
- **Datensätze vor 2021 werden ausgeschlossen** (24 Buchungen aus Jun–Aug 2020).
  Sie gehören nicht zu den beiden Vermietungsphasen.

## Betriebsphasen

| Phase | Vermietung | Buchbarkeitsfenster (Nenner der Auslastung) |
| --- | --- | --- |
| Renovierung 1 | – | bis Sep 2025 |
| **Phase 1** | Okt – Dez 2025 | **24.10.2025** – **13.12.2025** *(bestätigt: Vermietungsstart 24.10.2025; letzte Nacht 13.12.2025, Abreise des letzten Gastes 14.12.2025)* |
| Renovierung 2 | – | Jan – Apr 2026 |
| **Phase 2** | Mai – Okt 2026 | **22.05.2026** – 31.10.2026 *(bestätigt 02.11.2026: Betrieb lief ohne Saisonbruch weiter; letzte belegte Nacht 31.10., Abreise 01.11.2026)*, **10 Nächte gesperrt** (07.–16.08.) |

Die Renovierungsmonate und die **gesperrten Nächte** zählen **nicht** als
verfügbar. Phase 1 hat damit 51 Kalendertage (24.10.–13.12.2025), Phase 2 hat
163 Kalendertage (22.05.–31.10.2026) − 10 gesperrte = **153 verfügbare Nächte**.
Würde man die Sperre mitzählen, läge die Auslastung von Phase 2 fälschlich bei
86,5 % statt 92,2 %.

## Tabellen

### `buchungen.csv` (Fakt) – 53 Zeilen
| Spalte | Typ | Beschreibung |
| --- | --- | --- |
| `Buchung_ID` | Text | B001…B053, technisch vergeben |
| `Betriebsphase` | Text | zugeordnet über das **Anreisedatum** |
| `Waehrung` | Text | alle EUR |
| `Buchungsdatum` | Datum | Zeitpunkt der Buchung |
| `Anreise` | Datum | Check-in |
| `Abreise` | Datum | Check-out |
| `Naechte` | Ganzzahl | aus dem Export; stimmt bei allen Zeilen mit `Abreise − Anreise` überein |
| `Netto_Betrag` | Dezimal | Auszahlungsbetrag → **Umsatz** |
| `Servicegebuehr` | Dezimal | Airbnb-Gebühr (Bezugsgröße, s. u.) |
| `Brutto_Betrag` | Dezimal | `Netto_Betrag + Servicegebuehr` |
| `ADR_Netto` | Dezimal | `Netto_Betrag / Naechte` – **je Buchung**, nicht die Kennzahl |
| `Naechte_Belegt` | Ganzzahl | **Belegung**: nur Nächte, die dieser Aufenthalt exklusiv belegt |
| `Storno` | Text | „ja" bei stornierter, aber ausgezahlter Buchung |
| `Ueberlappung` | Text | „ja" bei zeitlicher Überschneidung mit einem anderen Aufenthalt |
| `Belegung_Hinweis` | Text | Klartext-Begründung zu `Storno` / `Ueberlappung` |
| `Vorlauf_Tage` | Ganzzahl | `Anreise − Buchungsdatum` |
| `Anreisetag_Wochentag` | Text | Wochentag der Anreise |
| `Jahr`, `Monat` | Ganzzahl | aus dem Anreisedatum |

**Wichtig – Umsatz ≠ Belegung.** `Netto_Betrag` ist der Umsatz,
`Naechte_Belegt` die Belegung. Beide können auseinanderfallen:

| Fall | Umsatz | Belegung |
| --- | --- | --- |
| Same-Day-Storno, Auszahlung erfolgte trotzdem | ja | **nein (0 Nächte)** |
| Verlängerung desselben Gastes, zwei Zahlungen | ja (2×) | **einmal (5 Nächte)** |

**`Naechte_Belegt` ist eine Vereinigung**, keine Summe: Überlappende
Aufenthaltszeiträume werden nur einmal gezählt. Ohne diese Regel zählt der
Mai-Fall 5 Nächte doppelt und der ADR sinkt künstlich um 6 %.

### `anpassungen.csv` (Fakt)
1 Zeile: `Mediations-Anpassung` (−30,00 €).
Die Anpassung −26,90 € vom 26.06.2020 ist ebenfalls ausgeschlossen (Entscheidung 1):
sie gehörte zu einer 2020er-Buchung und wäre ohne Gegenstück in `buchungen`
verwaist.

### `kalender.csv` (Dimension)
Täglich, 24.10.2025 – 01.11.2026 (bereinigt um die ausgeschlossenen 2020-Daten).
Spalten: `Datum`, `Jahr`, `Quartal`, `Monat`, `Monatsname`, `Kalenderwoche`,
`Wochentag`, **`Betriebsphase`**, **`Verfuegbar`** (ja/nein), **`Belegt`** (ja/nein),
**`Teilmonat`** (ja/nein)
– 11 Spalten, 374 Zeilen. **Als Datumstabelle markieren** (Spalte `Datum`).

`Monatsname` und `Wochentag` sind **deutsch** (`Oktober`, `Donnerstag`)
– festgelegt 02.11.2026. Auch `buchungen[Anreisetag_Wochentag]` ist deutsch.
Die Werte kommen aus `MONATSNAME`/`WOCHENTAG` in `build_kalender_tagesbasis.py`
und `build_datasets.py`, nicht aus `strftime` (das liefert englische Namen).

**`Teilmonat`** (ja/nein) markiert Monate, die das Buchbarkeitsfenster
anschneidet – **Okt 2025, Dez 2025, Mai 2026**. Ihre Auslastungsquote ist
**nicht** mit vollen Monaten vergleichbar: Sie haben weniger verfügbare Nächte,
und der Fensterausschnitt liest sich sonst als Nachfrage. Im Monatsvergleich
diese Monate ausblenden oder kennzeichnen (festgelegt 03.11.2026).
Ermittelt von `teilmonat_monate()` in `build_kalender_tagesbasis.py`.

Tage außerhalb der Buchbarkeitsfenster tragen die Phase
`Zwischenzeit (nicht buchbar)` mit `Verfuegbar = nein`. Erzeugt von
`build_kalender_tagesbasis.py` + `add_flags_to_kalender.py`.

> **Hinweis:** Diese Tabelle beginnt am 24.10.2025 und deckt damit Phase 1
> vollständig ab (Fensterstart = Tabellenstart). Die frühere Fassung mit
> Fensterstart 01.10.2025 ist überholt.

### `preisszenarien.csv` / `preisszenarien_monat.csv` (Szenario-Tabellen)

Erzeugt von `analyse/preisszenario.py` – **keine** Fakten, sondern eine fertige
Break-even-Rechnung für die Report-Seite „Preis testen". Je Zeile ein Preis-
schritt (−30 % … +30 %), je Basis (`gesamt`, `Phase 1`, `Phase 2`) bzw. je Monat.

| Spalte | Typ | Beschreibung |
| --- | --- | --- |
| `Preis_Delta_Pct` | Zahl | Preisänderung in Prozentpunkten (−30 … +30) |
| `Preis_je_Nacht_EUR` | Zahl | ADR × (1 + Delta) |
| `Umsatz_Konstant_EUR` | Zahl | Umsatz, wenn die Auslastung **konstant** bleibt – reine Preiswirkung |
| `Break_even_Naechte` | Zahl | heutiger Umsatz ÷ neuer Preis |
| `Break_even_Auslastung_Pct` | Zahl | Break-even-Nächte ÷ verfügbare Nächte |
| `Ist_Auslastung_Pct` | Zahl | heutige Auslastung – der Vergleichswert |
| `Ampel` | Text | `gruen` / `rot` / `unmoeglich` / `referenz` |
| `Hinweis` | Text | Klartext, z. B. „braucht 11,1 % mehr" |
| `Zeilenfarbe` | Text | Hex nur in der Referenzzeile (`#E8EEF4`), sonst leer |

Im Monats-Blatt zusätzlich: `Monat` (Text, für den Slicer), `Monat_Sort`
(Sortierschlüssel), `Monat_Datum` (**letzter** Tag des Monats), `Belegte_Naechte`,
`Verfuegbare_Naechte`, `Teilmonat`.

**`Ampel` = `unmoeglich`:** Break-even-Auslastung über 100 % – die nötigen
Nächte gibt es gar nicht, die Preissenkung ist nicht kompensierbar.

**Monatszuordnung auf Tagesbasis:** Anders als bei `buchungen` (dort zählt der
Anreisemonat) werden Nächte und Auslastung hier aus `kalender.csv` gezogen –
eine Nacht zählt in den Monat, in dem sie **liegt**. Sonst landete ein Aufenthalt
28.09.–03.10. komplett im September und der Oktober wäre zu leer.

### `treiber_*.csv` (Seite „Buchungstreiber")

Erzeugt von `analyse/buchungstreiber.py` – **keine** Fakten, sondern fertige
Tabellen für die Report-Seite „Buchungstreiber". Deutsche Schreibweise.

| Datei | Inhalt | Zeilen |
| --- | --- | --- |
| `treiber_wochentag.csv` | Auslastung je Wochentag (`Wochenende` = ja/nein für die Farbe, `Sort` = Mo–So) | 7 |
| `treiber_verteilung.csv` | Buchungen je `Dimension` (`Anreisetag` / `Aufenthalt` / `Vorlauf`) und `Auspraegung` | 17 |
| `treiber_modell.csv` | Modellergebnisse: `Effekt_Typ`, `Effekt`, `KI_unten`, `KI_oben`, `p_Wert`, `Signifikant`, `Lesart` | 5 |
| `treiber_luecken.csv` | unbelegte buchbare Tage je Monat | 8 |

**Die Statistik rechnet Python, nicht Power BI.** `treiber_modell.csv`
enthält die Ergebnisse eines Logit (geclusterte Standardfehler nach
Belegungsepisode) und eines OLS (HC3, Buchungsebene). Power BI kann das
nicht nachrechnen – die Seite zeigt die Tabelle nur an. `Signifikant` = ja
bei p < 0,05.

**Prozentpunkt-Zahlen:** `Auslastung_Pct` und `Anteil_Pct` stehen als Zahl
(86,21 = 86,21 %) – **kein** Prozentformat darauf legen.

## Bekannte Fallen im Rohdaten-Export

**1. Gemischte Dezimaltrenner in einer Datei.**
`Betrag` und `Ausgezahlt` nutzen den **Punkt** (`300.93`),
`Servicegebühr` nutzt das **Komma** (`68,07`). Wer blind mit einem
Landesformat parst, bekommt Faktor-100-Fehler. Gelöst in `build_datasets.py`.

**2. Payout-Zeilen sind keine Umsätze.**
100 der 155 Rohzeilen sind `Typ = Payout` – Auszahlungsereignisse, die jede
Buchung **spiegeln**. Wer naiv über `Betrag` summiert, zählt doppelt.
Deshalb: nur `Typ = Buchung` in die Faktentabelle.

**3. Gebührenmodell-Sprung – die teuerste Falle im Datensatz.**

| Zeitraum | Servicegebühr-Anteil |
| --- | --- |
| Phase 1 (Okt–Dez 2025) | ~3,6 % |
| Phase 2 (Mai–Okt 2026) | ~18,4 % |

Airbnb hat das Modell umgestellt. **Bruttobeträge sind über die Phasen nicht
vergleichbar**, der Netto-Betrag schon. Auswirkung: Bei gleichbleibendem
Netto-Erlös stieg der Listenpreis je Nacht von 58,81 € auf 71,21 € (+21,1 %).
Zum reinen Gebührenausgleich wären 18,3 % nötig gewesen – die Differenz ist
der gewonnene Preisspielraum.

**4. Personenbezug in der Details-Spalte.**
`Details` enthält die Zahlungsadresse des Hosts (E-Mail).
Die Spalte wird **nicht** übernommen – weder im Modell noch im Repository.

**5. Überlappende Aufenthalte – geklärt.**

| Buchung | Zeitraum | Netto | Ursache |
| --- | --- | --- | --- |
| 24.–27.09.2026 | 3 N | 127,43 € | **Storno**, Auszahlung erfolgte trotzdem |
| 25.–28.09.2026 | 3 N | 186,76 € | reguläre Neubuchung |
| 22.–27.05.2026 | 5 N | 170,44 € | reguläre Buchung |
| 22.–27.05.2026 | 5 N | 98,69 € | **Verlängerung** desselben Gastes |

Beide Fälle sind in `Storno` / `Ueberlappung` markiert und im Report
offengelegt – nicht stillschweigend entfernt.

**6. Ein Payout ohne Gegenbuchung.**
Im August 2026 liegt die Payout-Summe 30,00 € unter der Buchungssumme –
das ist die `Mediations-Anpassung` vom 18.08.2026. Kein Fehler, sondern eine
Korrekturzeile, die in `anpassungen.csv` separat geführt wird.

## Gebührenmodell: drei Preisebenen

Airbnb hat zwischen den Phasen das Modell gewechselt. Das ist der wichtigste
Kontext des Datensatzes – ohne ihn ist jede Preisaussage falsch.

| Phase | Modell | Host-Gebühr (belegt) | Gästegebühr |
| --- | --- | --- | --- |
| 1 (Okt–Dez 2025) | Split Fee | 3,57 % (= 3 % + MwSt.) | 14,1–16,5 % (Airbnb-Doku) |
| 2 (Mai–Okt 2026) | Host-Only Fee | 18,45 % (= 15,5 % + MwSt.) | 0 % – im Preis enthalten |

Die Host-Gebühren sind **aus den Daten belegt** (`Servicegebühr / Bruttoeinkünfte`).
Die Gästegebühr der Phase 1 ist **nicht am eigenen Konto messbar** – der
Host-Export enthält sie nicht. Laut Airbnb-Hilfecenter (Artikel 1857) liegt sie
im Split-Fee-Modell bei **14,1 % bis 16,5 %** der Buchungszwischensumme
(Nachtpreis + gastgeberseitige Gebühren, ohne Gästegebühr und Steuern) – das
entspricht exakt der Spalte `Bruttoeinkünfte`. Die MwSt. ist dort laut Airbnb
bereits enthalten. Arbeitswert für Berechnungen: **15 %**.

### Drei Preisebenen

| Ebene | Definition | Phase 1 | Phase 2 |
| --- | --- | --- | --- |
| **Auszahlung (netto)** | was beim Vermieter ankommt | `Betrag` | `Betrag` |
| **Listenpreis** | was der Gast als Zimmerpreis sieht | `Bruttoeinkünfte` | `Bruttoeinkünfte` |
| **Gast-Endpreis** | was der Gast tatsächlich zahlt | Listenpreis × (1 + Gästegebühr) | = Listenpreis |

> **Die Falle:** Die Spalte `Bruttoeinkünfte` bedeutet in beiden Phasen etwas
> anderes. In Phase 1 ist sie der Listenpreis *ohne* Gästegebühr, in Phase 2 der
> *Endpreis* des Gastes. Ein naiver Brutto-Vergleich vergleicht deshalb zwei
> verschiedene Dinge.

## Annahmen & Einschränkungen

- **Verfügbare Nächte:** nur die Buchbarkeitsfenster der Phasen; Renovierungs-
  monate sind kein Bestandteil des Nenners.
- **Buchungszuordnung:** In `buchungen.csv` wird eine Buchung dem Monat ihrer
  **Anreise** zugerechnet (so zählt Airbnb selbst). Für die **Monats-Auslastung**
  in `preisszenarien_monat.csv` gilt dagegen die **Tagesbasis** aus
  `kalender.csv`: eine Nacht zählt in den Monat, in dem sie liegt.
- **Beide Fenster sind bestätigt.** Phase 1: 24.10.–13.12.2025 (Stand 12.10.2026; der
  14.12.2025 ist nur der Abreisetag). Phase 2: 22.05.–31.10.2026 (Stand 02.11.2026; der
  01.11.2026 ist nur der Abreisetag). Ändert sich das Datum erneut, in `betriebsphasen`
  **und** in `build_datasets.py`, `build_kalender_tagesbasis.py` und
  `reports/build_xlsx.py` anpassen.
- **Gesperrte Nächte** (Eigennutzung, Reparatur) sind im Export nicht sichtbar;
  die Auslastung ist dadurch eine **Obergrenze**.
- **Kosten fehlen** (Nebenkosten, Reinigung, Instandhaltung) → kein Deckungsbeitrag.
- **Korrelation, nicht Kausalität:** Die Treiberanalyse (`treiber_*.csv`)
  zeigt Zusammenhänge. Der Preis ist selbst gesetzt, der Wochentag nicht –
  nur der Wochentag ist exogen. Modell A stützt sich auf 28 unbelegte Tage;
  mehr als zwei Prädiktoren wären damit unseriös.
- **Keine saisonale Aussage** und kein YoY: Phase 1 (Herbst/Winter) und Phase 2
  (Sommer) sind nicht vergleichbar genug für kausale Aussagen.
