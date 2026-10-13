# Datenwörterbuch

Quelle, Spalten, Typen, Bereinigungsregeln – und die Fallen, die im Export stecken.

## Quelle

| Quelle | Format | Inhalt | Zeitraum |
| --- | --- | --- | --- |
| Airbnb-Einnahmen-Export | CSV (UTF-8 BOM) | Buchungen, Payouts, Anpassungen | Jun 2020 – Okt 2026 |
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
| **Phase 2** | Mai – Sep 2026 | **22.05.2026** – 30.09.2026 *(bestätigt)*, **10 Nächte gesperrt** (07.–16.08.) |

Die Renovierungsmonate und die **gesperrten Nächte** zählen **nicht** als
verfügbar. Phase 1 hat damit 51 Kalendertage (24.10.–13.12.2025), Phase 2 hat
132 Kalendertage − 10 gesperrte = **122 verfügbare Nächte**. Würde man die
Sperre mitzählen, läge die Auslastung von Phase 2 fälschlich bei 84,1 % statt
91,0 %.

## Tabellen

### `buchungen.csv` (Fakt) – 44 Zeilen
| Spalte | Typ | Beschreibung |
| --- | --- | --- |
| `Buchung_ID` | Text | B001…B044, technisch vergeben |
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
Täglich, 24.10.2025 – 03.10.2026 (bereinigt um die ausgeschlossenen 2020-Daten).
Spalten: `Datum`, `Jahr`, `Quartal`, `Monat`, `Monatsname`, `Kalenderwoche`,
`Wochentag`, **`Betriebsphase`**, **`Verfuegbar`** (ja/nein), **`Belegt`** (ja/nein)
– 10 Spalten, 345 Zeilen. **Als Datumstabelle markieren** (Spalte `Datum`).

Tage außerhalb der Buchbarkeitsfenster tragen die Phase
`Zwischenzeit (nicht buchbar)` mit `Verfuegbar = nein`. Erzeugt von
`build_kalender_tagesbasis.py` + `add_flags_to_kalender.py`.

> **Hinweis:** Diese Tabelle beginnt am 24.10.2025 und deckt damit Phase 1
> vollständig ab (Fensterstart = Tabellenstart). Die frühere Fassung mit
> Fensterstart 01.10.2025 ist überholt.

## Bekannte Fallen im Rohdaten-Export

**1. Gemischte Dezimaltrenner in einer Datei.**
`Betrag` und `Ausgezahlt` nutzen den **Punkt** (`300.93`),
`Servicegebühr` nutzt das **Komma** (`68,07`). Wer blind mit einem
Landesformat parst, bekommt Faktor-100-Fehler. Gelöst in `build_datasets.py`.

**2. Payout-Zeilen sind keine Umsätze.**
67 der 137 Rohzeilen sind `Typ = Payout` – Auszahlungsereignisse, die jede
Buchung **spiegeln**. Wer naiv über `Betrag` summiert, zählt doppelt.
Deshalb: nur `Typ = Buchung` in die Faktentabelle.

**3. Gebührenmodell-Sprung – die teuerste Falle im Datensatz.**

| Zeitraum | Servicegebühr-Anteil |
| --- | --- |
| Phase 1 (Okt–Dez 2025) | ~3,6 % |
| Phase 2 (Mai–Sep 2026) | ~18,4 % |

Airbnb hat das Modell umgestellt. **Bruttobeträge sind über die Phasen nicht
vergleichbar**, der Netto-Betrag schon. Auswirkung: Bei gleichbleibendem
Netto-Erlös stieg der Bruttopreis je Nacht von 58,81 € auf 70,33 € (+20 %).
Zum reinen Gebührenausgleich wären 18,1 % nötig gewesen – die Differenz ist
der verlorene Preisspielraum.

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
| 2 (Mai–Sep 2026) | Host-Only Fee | 18,45 % (= 15,5 % + MwSt.) | 0 % – im Preis enthalten |

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
- **Buchungszuordnung:** Eine Buchung wird dem Monat ihrer **Anreise** zugerechnet.
- **Phase-1-Fenster ist bestätigt** (24.10.–13.12.2025, Stand 12.10.2026; der
  14.12.2025 ist nur der Abreisetag). Ändert sich das Datum erneut, in `betriebsphasen`
  **und** in `build_datasets.py`, `build_kalender_tagesbasis.py` und
  `build_phasenvergleich.py` anpassen.
- **Gesperrte Nächte** (Eigennutzung, Reparatur) sind im Export nicht sichtbar;
  die Auslastung ist dadurch eine **Obergrenze**.
- **Kosten fehlen** (Nebenkosten, Reinigung, Instandhaltung) → kein Deckungsbeitrag.
- **Keine saisonale Aussage** und kein YoY: Phase 1 (Herbst/Winter) und Phase 2
  (Sommer) sind nicht vergleichbar genug für kausale Aussagen.
