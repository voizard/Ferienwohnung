# Measures – Definitionen

Spalten- und Measure-Ebene für das Modell aus `daten/buchungen.csv`.
**Netto** = Betrag, den ich von Airbnb ausgezahlt bekomme.
**Brutto** = Netto + Airbnb-Servicegebühr (Bezugsgröße der Gebühr, nicht der Gästepreis).

---

## 1. Datumstabelle

Entweder aus `daten/kalender.csv` importieren **oder** in DAX berechnen:

```dax
kalender =
    VAR MinDatum = MIN ( buchungen[Anreise] )
    VAR MaxDatum = MAX ( buchungen[Abreise] )
    RETURN
        ADDCOLUMNS (
            CALENDAR ( MinDatum, MaxDatum ),
            "Jahr", YEAR ( [Date] ),
            "Quartal", QUARTER ( [Date] ),
            "Monat", MONTH ( [Date] ),
            "Monatsname", FORMAT ( [Date], "MMM" ),
            "Kalenderwoche", WEEKNUM ( [Date], 2 ),
            "Wochentag", FORMAT ( [Date], "ddd" )
        )
```

Danach: **Als Datumstabelle markieren** (Rechtsklick → *Als Datumstabelle markieren* → Spalte `Date`).
Ohne diesen Schritt liefern `SAMEPERIODLASTYEAR` & Co. falsche Ergebnisse.

**Beziehung:** `kalender[Date]` (1) → `buchungen[Anreise]` (*)

> Hinweis: Die Zuordnung erfolgt über die **Anreise**. Eine Buchung wird also dem
> Monat ihres Check-ins zugerechnet. Für Umsatz pro Monat ist das die übliche
> und nachvollziehbare Konvention – im Datenwörterbuch dokumentiert.

---

## 1b. Tages-Tabelle – damit EIN Measure reicht

Die Tabelle **`daten/kalender_tagesbasis.csv`** (345 Zeilen, 2025-10-24 → 2026-10-03,
erzeugt von `daten/build_kalender_tagesbasis.py`) hat **eine Zeile pro Tag** und deckt
exakt denselben Zeitraum wie die alte `kalender`-Tabelle ab – sie lässt sich also
**1:1 über `Datum` zusammenführen**:

| Spalte | Inhalt |
| --- | --- |
| `Datum` | Tagesdatum |
| `Jahr` / `Quartal` / `Monat` / `Monatsname` / `Kalenderwoche` / `Wochentag` | Zeitattribute |
| `Betriebsphase` | Phasenname oder `Zwischenzeit (nicht buchbar)` |
| `Verfuegbar` | `ja`/`nein` – Tag liegt im Buchbarkeitsfenster und ist nicht gesperrt |
| `Belegt` | `ja`/`nein` – ein Aufenthalt (ohne Storno) überdeckt den Tag |

Weil **tageweise** gezählt wird, sind Überlappungen, Verlängerungen und Überhänge
automatisch korrekt. Ein einziges Measure funktioniert dann in **jedem** Kontext –
Card, Slicer, Matrix nach Phase, Matrix nach Monat:

```dax
Auslastung % =
DIVIDE (
    CALCULATE ( COUNTROWS ( kalender ), kalender[Belegt] = "ja" ),
    CALCULATE ( COUNTROWS ( kalender ), kalender[Verfuegbar] = "ja" )
)
```

`kalender[Datum]` als Datumstabelle markieren. Die Beziehung `kalender[Datum]` (1) →
`buchungen[Anreise]` (*) kann bleiben (Umsatz nach Check-in-Monat), für die Auslastung
wird sie nicht gebraucht.

**Verifizierte Werte** (aus `kalender_tagesbasis.csv`):

| Kontext | Belegt | Verfügbar | Auslastung |
| --- | --- | --- | --- |
| gesamt | 146 | 173 | **84,4 %** |
| Phase 1 (24.10.–13.12.2025) | 35 | 51 | **68,6 %** |
| Phase 2 (Mai–Sep 2026) | 111 | 122 | **91,0 %** |
| Okt 2025 (ab 24.) | 3 | 8 | 37,5 % |
| Nov 2025 | 27 | 30 | 90,0 % |
| Dez 2025 (bis 13.) | 5 | 13 | 38,5 % |
| Mai 2026 (ab 22.) | 9 | 10 | 90,0 % |
| Jun 2026 | 25 | 30 | 83,3 % |
| Jul 2026 | 28 | 31 | 90,3 % |
| Aug 2026 (abzgl. 10 gesperrt) | 21 | 21 | **100,0 %** |
| Sep 2026 | 28 | 30 | 93,3 % |

> Mit dieser Tabelle werden die Measures aus Abschnitt 4 (`Auslastung % je Phase`,
> `Auslastung % Phase 1/2`, `Gesperrte Naechte`, `Verfuegbare Naechte`) **überflüssig**.
> Sie bleiben hier nur als Weg ohne Zusatztabelle stehen.

---

## 2. Betriebsphasen (die zentrale Annahme)

Die Wohnung war nicht durchgehend vermietbar. Damit die Auslastung stimmt,
müssen die Renovierungsmonate aus dem Nenner raus. Dafür eine kleine
Hilfstabelle – sie dokumentiert die Annahme sichtbar im Modell:

```dax
betriebsphasen =
DATATABLE (
    "Betriebsphase", STRING,
    "Verfuegbar_ab", DATETIME,
    "Verfuegbar_bis", DATETIME,
    {
        { "Phase 0 (2020)", DATE ( 2020, 6, 10 ), DATE ( 2020, 8, 31 ) },
        { "Phase 1 (Okt-Dez 2025)", DATE ( 2025, 10, 24 ), DATE ( 2025, 12, 13 ) },
        { "Phase 2 (Mai-Sep 2026)", DATE ( 2026, 5, 1 ), DATE ( 2026, 9, 30 ) }
    }
)
```

`Verfuegbar_ab`/`Verfuegbar_bis` = Zeitraum, in dem die Wohnung **buchbar** war.
**Diese Werte sind Annahmen und müssen stimmen** – sie steuern die Auslastung direkt.
Falls das Inserat erst später online ging, hier das echte Datum eintragen.

Beziehung: `betriebsphasen[Betriebsphase]` (1) → `buchungen[Betriebsphase]` (*)

---

## 3. Basisgrößen

```dax
Anzahl Buchungen = DISTINCTCOUNT ( buchungen[Buchung_ID] )

Naechte = SUM ( buchungen[Naechte] )

-- Belegung ≠ Buchungsnächte: `Naechte_Belegt` zählt überlappende/verlängerte
-- Zeiträume nur einmal und Storno-Nächte gar nicht. Für Auslastung, ADR und
-- Ø Aufenthalt gehört die BELEGUNG in den Zähler, nicht `Naechte`.
Belegte Naechte = SUM ( buchungen[Naechte_Belegt] )

Umsatz Netto = SUM ( buchungen[Netto_Betrag] )
Umsatz Brutto = SUM ( buchungen[Brutto_Betrag] )
Servicegebuehren = SUM ( buchungen[Servicegebuehr] )
```

---

## 4. Kennzahlen

```dax
-- Einzeiler-Variante OHNE zweite Measure (damit kann „… kann nicht gefunden
-- werden" nicht mehr auftreten). Die Sperre ist phasengebunden: nur Phase 2
-- hat 07.–16.08.2026 = 10 Nächte.
Verfuegbare Naechte =
    SUMX (
        betriebsphasen,
        DATEDIFF ( betriebsphasen[Verfuegbar_ab], betriebsphasen[Verfuegbar_bis], DAY ) + 1
    )
    - IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Sep 2026)", 10, 0 )
```

```dax
-- Gesperrte Nächte (Eigennutzung/Instandhaltung) sind NICHT verfügbar.
-- Phase 2: 07.–16.08.2026 = 10 Nächte. Ohne diesen Abzug wäre die
-- Auslastung von Phase 2 fälschlich 84,1 % statt 91,0 %.
--
-- ⚠️ Phasenfalle: eine eigenständige Measure OHNE Phasenbezug liefert in JEDER
-- Zeile 10 – auch in Phase 1 (Okt–Dez 2025), wo nichts gesperrt ist. Phase 1
-- wäre dann 35/41 = 85,4 % statt korrekt 35/51 = 68,6 %. Deshalb phasengebunden:
Gesperrte Naechte =
    IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Sep 2026)", 10, 0 )

-- Saubere Dauerlösung (statt der festen 10): eigene Tabelle `sperrzeiten` mit
-- Betriebsphase-Spalte + Beziehung betriebsphasen[Betriebsphase] (1) →
-- sperrzeiten[Betriebsphase] (*). Dann ist die Sperre automatisch phasengebunden:
--
--   sperrzeiten = DATATABLE ( "Betriebsphase", STRING, "Ab", DATETIME, "Bis", DATETIME,
--       { { "Phase 2 (Mai-Sep 2026)", DATE ( 2026, 8, 7 ), DATE ( 2026, 8, 16 ) } } )
--
--   Gesperrte Naechte = SUMX ( sperrzeiten, DATEDIFF ( sperrzeiten[Ab], sperrzeiten[Bis], DAY ) + 1 )
--
-- Merksatz: Measures ruft man OHNE Tabellenpräfix auf (`[Gesperrte Naechte]`).
-- `buchungen[Gesperrte Naechte]` sucht eine SPALTE → „kann nicht gefunden werden".
```

```dax
Auslastung % = DIVIDE ( [Belegte Naechte], [Verfuegbare Naechte] )
```

**Auslastung je Betriebsphase – das vollständige Measure.** Rechnet die Belegung
phasengenau (Nächte, die über das Fensterende hinausragen, werden abgeschnitten;
Zeilen ohne exklusive Belegung – Verlängerung/Storno – fallen raus). Selbstständig,
braucht keine der Measures oben:

```dax
Auslastung % je Phase =
VAR Verfuegbar =
    SUMX (
        betriebsphasen,
        DATEDIFF ( betriebsphasen[Verfuegbar_ab], betriebsphasen[Verfuegbar_bis], DAY ) + 1
    )
        - IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Sep 2026)", 10, 0 )
VAR Belegt =
    SUMX (
        FILTER ( buchungen, buchungen[Naechte_Belegt] > 0 ),
        VAR Ab = MAX ( buchungen[Anreise], MIN ( betriebsphasen[Verfuegbar_ab] ) )
        VAR Bis = MIN ( buchungen[Abreise], MAX ( betriebsphasen[Verfuegbar_bis] ) + 1 )
        RETURN
            MAX ( 0, Bis - Ab )
    )
RETURN
    DIVIDE ( Belegt, Verfuegbar )
```

**Verifizierte Werte** (aus `buchungen.csv`, 44 Zeilen nachgerechnet):

| Betriebsphase | Belegt | Verfügbar | Auslastung |
| --- | --- | --- | --- |
| Phase 1 (24.10.–13.12.2025) | 35 | 51 | **68,6 %** |
| Phase 2 (Mai–Sep 2026) | 111 | 122 | **91,0 %** |
| beide ausgewählt | 146 | 173 | 84,4 % |
| keine Auswahl (inkl. Phase 0) | 146 | 256 | 57,0 % — **bedeutungslos** |

Ohne die Abschneide-Logik wären es 113/122 = **92,6 %** – das ist der Wert mit dem
2-Nächte-Überhang von **B001** (Anreise 28.09.2026, Abreise 03.10.2026: 5 Nächte
gebucht, davon 3 im Fenster). Die Report-Zahl **91,0 %** ist die phasengenaue.

**Alternative: ein Measure pro Phase.** Beide sind vollständig selbstständig – sie
ignorieren Slicer und Filterkontext und liefern immer die Zahl ihrer eigenen Phase.
Damit stehen beide Quoten gleichzeitig in zwei Cards, ohne Visual-Filter und ohne
Interaktionen abschalten zu müssen.

```dax
Auslastung % Phase 1 =
VAR Phase = "Phase 1 (Okt-Dez 2025)"
VAR Ab = CALCULATE ( MIN ( betriebsphasen[Verfuegbar_ab] ), betriebsphasen[Betriebsphase] = Phase )
VAR Bis = CALCULATE ( MAX ( betriebsphasen[Verfuegbar_bis] ), betriebsphasen[Betriebsphase] = Phase )
VAR Verfuegbar = ( Bis - Ab ) + 1
VAR Belegt =
    SUMX (
        FILTER ( buchungen, buchungen[Betriebsphase] = Phase && buchungen[Naechte_Belegt] > 0 ),
        MAX ( 0, MIN ( buchungen[Abreise], Bis + 1 ) - MAX ( buchungen[Anreise], Ab ) )
    )
RETURN
    DIVIDE ( Belegt, Verfuegbar )
```

```dax
Auslastung % Phase 2 =
VAR Phase = "Phase 2 (Mai-Sep 2026)"
VAR Ab = CALCULATE ( MIN ( betriebsphasen[Verfuegbar_ab] ), betriebsphasen[Betriebsphase] = Phase )
VAR Bis = CALCULATE ( MAX ( betriebsphasen[Verfuegbar_bis] ), betriebsphasen[Betriebsphase] = Phase )
VAR Verfuegbar = ( Bis - Ab ) + 1 - 10   -- 10 Nächte gesperrt: 07.–16.08.2026
VAR Belegt =
    SUMX (
        FILTER ( buchungen, buchungen[Betriebsphase] = Phase && buchungen[Naechte_Belegt] > 0 ),
        MAX ( 0, MIN ( buchungen[Abreise], Bis + 1 ) - MAX ( buchungen[Anreise], Ab ) )
    )
RETURN
    DIVIDE ( Belegt, Verfuegbar )
```

Werte: **Auslastung % Phase 1 = 68,6 %** (35/51) · **Auslastung % Phase 2 = 91,0 %** (111/122).

> Nebenwirkung: Beide Measures sind konstant – der Betriebsphasen-Slicer hat auf sie
> **keinen** Einfluss mehr. Wenn der Slicer die Quoten steuern soll, statt der festen
> Variante `Auslastung % je Phase` oben verwenden.

```dax
ADR Netto = DIVIDE ( [Umsatz Netto], [Belegte Naechte] )
```

### ADR je Phase („ADR pro Periode") – braucht KEINE neue Measure

`ADR Netto` rechnet im **aktuellen Filterkontext**. Sobald `Betriebsphase` im Visual
liegt (Matrix-Zeilen oder Slicer), liefert dieselbe Measure den Phasenwert.

| Kontext | Umsatz netto | Belegte Nächte | ADR netto |
| --- | --- | --- | --- |
| gesamt | 8.465,94 € | 148 | **57,20 €** |
| Phase 1 (Okt–Dez 2025) | 1.984,81 € | 35 | **56,71 €** |
| Phase 2 (Mai–Sep 2026) | 6.481,13 € | 113 | **57,36 €** |

Für **zwei Cards nebeneinander** (analog `Auslastung % Phase 1/2`) zwei feste Measures –
sie ignorieren Slicer und liefern immer ihre eigene Phase:

```dax
ADR Netto Phase 1 =
    CALCULATE (
        DIVIDE ( [Umsatz Netto], [Belegte Naechte] ),
        buchungen[Betriebsphase] = "Phase 1 (Okt-Dez 2025)"
    )
```

```dax
ADR Netto Phase 2 =
    CALCULATE (
        DIVIDE ( [Umsatz Netto], [Belegte Naechte] ),
        buchungen[Betriebsphase] = "Phase 2 (Mai-Sep 2026)"
    )
```

**Fällt `[Umsatz Netto]` als „nicht gefunden" auf** (Measure noch nicht angelegt),
dieselben zwei Measures **ohne jede Abhängigkeit** – nur mit Basisspalten:

```dax
ADR Netto Phase 1 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 1 (Okt-Dez 2025)"
    )
```

```dax
ADR Netto Phase 2 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 2 (Mai-Sep 2026)"
    )
```

**Drei Fallen**

1. **Nie `AVERAGE ( buchungen[ADR_Netto] )`.** Die Spalte ist der ADR *je Buchung*; der
   ungewichtete Mittelwert zählt kurze Aufenthalte gleich viel wie lange → Phase 1
   **59,19 €** statt 56,71 €, Phase 2 **56,20 €** statt 57,36 €. Richtig ist immer
   `Umsatz ÷ Nächte` (gewichtet).
2. **Storno zählt zum Umsatz, nicht zur Belegung.** B003 (127,43 €, 0 belegte Nächte)
   hebt den ADR von Phase 2 um +1,13 € (56,23 → 57,36). Bewusst so – das Geld ist real.
3. **Nenner ist die Belegung (`Naechte_Belegt`), nicht `Naechte`.** Sonst zählt B037
   (Verlängerung, 0 belegte Nächte) doppelt: 6.481,13 / 121 = 53,56 € statt 57,36 €.

Zähler und Nenner sind hier beide **buchungsbasiert** (Phase über die Anreise) und damit
in sich stimmig. Die *Auslastung* rechnet dagegen **tageweise** (111 statt 113 Nächte in
Phase 2, weil B001 mit 2 Nächten über den 30.09. hinausragt) – die beiden Kennzahlen
unterscheiden sich deshalb minimal, jede ist aber in ihrer eigenen Logik korrekt.
Strikt fenstergenau wäre 6.481,13 / 111 = 58,39 € – das mischt aber Umsatz *mit*
Überhang und Nächte *ohne* und ist deshalb nicht zu empfehlen.

```dax
RevPAR = DIVIDE ( [Umsatz Netto], [Verfuegbare Naechte] )
```

```dax
Ø Aufenthalt Naechte = DIVIDE ( [Belegte Naechte], [Anzahl Buchungen] )
```

```dax
Ø Vorlauf Tage = AVERAGE ( buchungen[Vorlauf_Tage] )
```

```dax
Ø Umsatz je Buchung = DIVIDE ( [Umsatz Netto], [Anzahl Buchungen] )
```

---

## 5. Zeitvergleiche

```dax
Umsatz Vormonat = CALCULATE ( [Umsatz Netto], DATEADD ( kalender[Date], -1, MONTH ) )
```

```dax
Naechte Vormonat = CALCULATE ( [Naechte], DATEADD ( kalender[Date], -1, MONTH ) )
```

> **Kein Jahresvergleich (YoY).** Die beiden Vermietungsphasen liegen in
> unterschiedlichen Jahren *und* unterschiedlichen Jahreszeiten. Ein YoY-Wert
> wäre in der Sache falsch. Verglichen wird über `Betriebsphase`, nicht über das Jahr.

### Entwicklung zwischen den Phasen (Differenz-Maßzahlen)

Für zwei Karten nebeneinander („Auslastung 68,6 % → 91,0 %", „ADR 56,71 € → 57,36 €").
Beide Maßzahlen sind **fest verdrahtet** – jede Phase wird per `CALCULATE` selbst gesetzt,
also zeigen sie in jeder Visualisierung denselben Wert und ignorieren Slicer.

Einfachste Fassung – nur möglich, wenn die beiden Phasen-Maßzahlen schon existieren
(`Auslastung % Phase 1` / `Auslastung % Phase 2`, die 68,6 % und 91,0 % zeigen):

```dax
Auslastung % Differenz P2-P1 = [Auslastung % Phase 2] - [Auslastung % Phase 1]
```

> **Warum die kurze Fassung 0 liefern kann:** `CALCULATE` filtert die *Tabelle*
> (`kalender`), nicht die Maßzahl. Holt `[Auslastung %]` ihre Zahlen aus einer anderen
> Tabelle (`betriebsphasen`, zweite Kalender-Tabelle, `ALL(...)`), ändert der
> `Betriebsphase`-Filter nichts – beide Phasen liefern denselben Wert, die Differenz ist
> exakt 0. Dann die selbstständige Fassung unten nehmen.

```dax
Auslastung % Differenz P2-P1 =
VAR P1 =
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 1 (Okt-Dez 2025)" )
VAR P2 =
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 2 (Mai-Sep 2026)" )
RETURN
    P2 - P1
```

```dax
ADR Differenz P2-P1 =
VAR P1 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 1 (Okt-Dez 2025)"
    )
VAR P2 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 2 (Mai-Sep 2026)"
    )
RETURN
    P2 - P1
```

Relative Fassung („um wie viel Prozent hat sich die Kennzahl verändert"):

```dax
Auslastung % Veraenderung P2-P1 =
VAR P1 =
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 1 (Okt-Dez 2025)" )
VAR P2 =
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 2 (Mai-Sep 2026)" )
RETURN
    DIVIDE ( P2, P1 ) - 1
```

```dax
ADR Veraenderung P2-P1 =
VAR P1 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 1 (Okt-Dez 2025)"
    )
VAR P2 =
    CALCULATE (
        DIVIDE ( SUM ( buchungen[Netto_Betrag] ), SUM ( buchungen[Naechte_Belegt] ) ),
        buchungen[Betriebsphase] = "Phase 2 (Mai-Sep 2026)"
    )
RETURN
    DIVIDE ( P2, P1 ) - 1
```

Sollwerte:

| Maßzahl | Ergebnis |
| --- | --- |
| `Auslastung % Differenz P2-P1` | **+22,4 Pp** (0,224) |
| `Auslastung % Veraenderung P2-P1` | **+32,6 %** |
| `ADR Differenz P2-P1` | **+0,65 €** |
| `ADR Veraenderung P2-P1` | **+1,1 %** |

**Fallen**

1. **Prozentpunkt ≠ Prozent.** Die Auslastungs-Differenz ist 0,224 – als Prozent formatiert
   steht dort „22,4 %". Wer das als relative Steigerung liest, liegt um Faktor 1,5 daneben
   (richtig: +32,6 %). Für eindeutige Beschriftung ein benutzerdefiniertes Format setzen:
   `+0,0" Pp";-0,0" Pp"`.
2. **Die ADR-Differenz nie über `AVERAGE ( buchungen[ADR_Netto] )` bilden** – ungewichtet
   ergibt das 59,19 € / 56,20 € und damit **−2,99 €** statt der richtigen **+0,65 €**.
3. **`[Auslastung %]` muss existieren.** Fehlt sie, dieselbe Rechnung abhängigkeitsfrei
   schreiben: Zähler `CALCULATE ( COUNTROWS ( kalender ), kalender[Belegt] = "ja" )`,
   Nenner `CALCULATE ( COUNTROWS ( kalender ), kalender[Verfuegbar] = "ja" )` – in beiden
   `VAR`-Blöcken.
4. **Die Differenz zeigt 0 oder (Leer).** Vier Ursachen, in dieser Reihenfolge prüfen:
   - `[Auslastung %]` **ignoriert den Phasenfilter** (z. B. `ALL(kalender)` oder `FILTER`
     über die ganze Tabelle) → beide Phasen liefern denselben Wert, die Differenz ist
     exakt 0. Dann die **phasenfreie Fassung** unten nehmen.
   - **Copy-Paste:** im zweiten `VAR` steht noch der Phasenname der Phase 1 → ebenfalls 0.
   - **Format:** 0,224 mit 0 Dezimalstellen zeigt „0" → Menüband *Measuretools* →
     Format **Prozent**, 1 Dezimalstelle.
   - **(Leer) statt 0:** der Phasenname im Filter passt nicht → exakten Text aus
     `kalender[Betriebsphase]` kopieren (Klammern, Bindestrich, Groß-/Kleinschreibung).

Phasenfreie Fassung (kann an keinem Phasennamen scheitern):

```dax
Auslastung % Differenz P2-P1 =
VAR P1Belegt =
    CALCULATE ( COUNTROWS ( kalender ), kalender[Belegt] = "ja",
        kalender[Datum] >= DATE ( 2025, 10, 24 ), kalender[Datum] <= DATE ( 2025, 12, 13 ) )
VAR P1Verf =
    CALCULATE ( COUNTROWS ( kalender ), kalender[Verfuegbar] = "ja",
        kalender[Datum] >= DATE ( 2025, 10, 24 ), kalender[Datum] <= DATE ( 2025, 12, 13 ) )
VAR P2Belegt =
    CALCULATE ( COUNTROWS ( kalender ), kalender[Belegt] = "ja",
        kalender[Datum] >= DATE ( 2026, 5, 22 ), kalender[Datum] <= DATE ( 2026, 9, 30 ) )
VAR P2Verf =
    CALCULATE ( COUNTROWS ( kalender ), kalender[Verfuegbar] = "ja",
        kalender[Datum] >= DATE ( 2026, 5, 22 ), kalender[Datum] <= DATE ( 2026, 9, 30 ) )
RETURN
    DIVIDE ( P2Belegt, P2Verf ) - DIVIDE ( P1Belegt, P1Verf )
```

> Die gesperrten Nächte 07.–16.08.2026 brauchen hier keine eigene Zeile – sie tragen in
> `kalender` bereits `Verfuegbar = nein` und fallen aus dem Nenner.

### Pfeil und Farbe für die Differenz (Unicode)

Eine einzelne Textmaßzahl lässt sich in Power BI nicht teilweise einfärben. Deshalb
**zwei** Maßzahlen: eine für den Text (Pfeil + Wert), eine für die Farbe – die Farbe wird
per bedingter Formatierung an die Textmaßzahl gehängt.

```dax
Auslastung % Delta =
VAR Delta = [Auslastung % Differenz P2-P1]
RETURN
    IF (
        ISBLANK ( Delta ),
        "–",
        IF ( Delta >= 0, "▲ ", "▼ " ) & FORMAT ( ABS ( Delta ) * 100, "0.0" ) & " Pp"
    )
```

```dax
Auslastung % Delta Farbe =
VAR Delta = [Auslastung % Differenz P2-P1]
RETURN
    IF ( ISBLANK ( Delta ), "#808080", IF ( Delta >= 0, "#1E7B34", "#C62828" ) )
```

```dax
ADR Delta =
VAR Delta = [ADR Differenz P2-P1]
RETURN
    IF (
        ISBLANK ( Delta ),
        "–",
        IF ( Delta >= 0, "▲ ", "▼ " ) & FORMAT ( ABS ( Delta ), "0.00" ) & " €"
    )
```

```dax
ADR Delta Farbe =
VAR Delta = [ADR Differenz P2-P1]
RETURN
    IF ( ISBLANK ( Delta ), "#808080", IF ( Delta >= 0, "#1E7B34", "#C62828" ) )
```

**Anwenden (Karte):** Karte markieren → Formatierungsbereich (Pinsel) → **Callout-Wert** →
**Farbe** → **fx** → Formatstil **Feldwert** → Feld `… Delta Farbe`. In Matrix/Tabelle
stattdessen **Zellen-Elemente → Schriftfarbe → fx**.

Ergebnis: `▲ 22,4 Pp` in Grün bzw. `▲ 0,65 €` in Grün – bei negativer Entwicklung
entsprechend `▼` in Rot.

**Hinweise**

- Der Dezimaltrenner kommt aus der Modellsprache (deutsches Modell → Komma).
- `ABS ( Delta ) * 100` statt eines `%`-Formats: der `%`-Platzhalter multipliziert in DAX
  ebenfalls mit 100, so ist es aber eindeutig und die Einheit bleibt frei wählbar
  (`" Pp"` / `" %"`).
- **Textmaßzahlen sind nicht sortierbar** und nicht weiter rechenbar. In Tabellen die
  numerische Maßzahl behalten und nur die Anzeige bedingt formatieren.
- Pfeil-Alternativen: `▲ ▼` (kompakt, gut in Karten), `↑ ↓` (feiner), `🟢 🔴` (bringen die
  Farbe selbst mit – dann ist keine bedingte Formatierung nötig).

---

## 6. Datenqualität sichtbar machen

```dax
Buchungen mit Überlappung =
    CALCULATE ( [Anzahl Buchungen], buchungen[Ueberlappung_Verdacht] = "ja" )
```

Bei 0 Buchungen: keine gefundenen Überschneidungen. Sonst auf einer
„Datenqualität"-Seite als Warnhinweis darstellen – offener Umgang mit
Datenzweifeln zählt im Portfolio mehr als ein glattes Dashboard.

---

## 7. Warum kein Brutto-ADR-Vergleich

### Drei Preisebenen – der wichtigste Kontext des Datensatzes

Airbnb hat zwischen den Phasen das Gebührenmodell umgestellt.

| Phase | Modell | Host-Gebühr | Gästegebühr |
| --- | --- | --- | --- |
| 1 (Okt–Dez 2025) | Split Fee | 3 % + MwSt. = **3,57 %** | **14,1–16,5 %**, im Checkout sichtbar ¹ |
| 2 (Mai–Sep 2026) | Host-Only Fee | 15,5 % + MwSt. = **18,45 %** | 0 % – im Preis enthalten |

Daraus folgen **drei Preisebenen**, die nicht dasselbe sind:

| Ebene | Definition | Phase 1 | Phase 2 |
| --- | --- | --- | --- |
| **Auszahlung (netto)** | was beim Vermieter ankommt | `Betrag` | `Betrag` |
| **Listenpreis** | was der Gast als Zimmerpreis sieht | `Bruttoeinkünfte` | `Bruttoeinkünfte` |
| **Gast-Endpreis** | was der Gast tatsächlich zahlt | Listenpreis × (1 + Gästegebühr) | = Listenpreis |

> **Die Falle:** Die Spalte `Bruttoeinkünfte` bedeutet in beiden Phasen etwas
> anderes. In Phase 1 ist sie der Listenpreis *ohne* Gästegebühr, in Phase 2 der
> *Endpreis* des Gastes. Ein Brutto-Vergleich über die Phasen vergleicht deshalb
> zwei verschiedene Dinge – der Host-Export enthält die Gästegebühr
> **strukturell nicht**.

**Vergleichbare Größen:**
- Eigene Wirtschaftlichkeit → **Auszahlung (netto)**, `Umsatz Netto`
- Gästesicht → **Gast-Endpreis**, in Phase 2 = `Umsatz Brutto`, in Phase 1 × (1 + Gästegebühr)

> ¹ **Gästegebühr: belegter Bereich, keine Messung am eigenen Konto.** Der
> Host-Export enthält sie strukturell nicht. Laut Airbnb-Hilfecenter (Art. 1857)
> beträgt die Gästegebühr im Split-Fee-Modell **14,1 % bis 16,5 %** der
> Buchungszwischensumme (= Nachtpreis + gastgeberseitige Gebühren – genau die
> Spalte `Bruttoeinkünfte`). Die MwSt. ist dort laut Airbnb **bereits enthalten**,
> es kommt also nichts obendrauf. Gerechnet wird mit **15 %** als Arbeitswert.
> Die Schlussfolgerungen sind über das ganze Band stabil
> (Gastpreis-Δ +2,7 % bis +4,8 %).
>
> *Gegenprobe Host-Gebühr:* Airbnb nennt für die einheitliche Gebühr 15,5 %.
> Die Daten zeigen 14,58 / 79,00 = **18,45 %** = 15,5 % × 1,19 – hier ist die
> MwSt. also **aufgeschlagen**, nicht enthalten. Für das eigene Konto gilt der
> gemessene Wert, nicht der Help-Center-Wert.

**Warum die Preiserhöhung nötig war.**
Damit dieselbe *Auszahlung* herauskommt, muss der Listenpreis mit
`(1 − 3,57 %) / (1 − 18,45 %) = 1,183` multipliziert werden → **+18,3 %**.
Tatsächlich gestiegen: **+19,6 %**. Die Auszahlung je Nacht blieb dadurch
praktisch konstant (56,71 € → 57,36 €). Die Erhöhung war also **richtig
bemessen**: sie hat genau die Gebühr kompensiert und den Netto-Preis stabil
gehalten – mehr aber auch nicht.

```dax
Listenpreis je Nacht = DIVIDE ( [Umsatz Brutto], [Belegte Naechte] )
```

**Der Multiplikator-Effekt.** Jede künftige Netto-Erhöhung um 1 € verlangt jetzt
eine Listenpreis-Erhöhung von `1 / 0,8155 = 1,23 €`. Vor der Umstellung waren es
`1 / 0,9643 = 1,04 €`. Der Preisspielraum ist damit strukturell enger geworden –
ein Nachteil des Host-Only-Modells, unabhängig von der Auslastung.
