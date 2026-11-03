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
            "Monatsname", FORMAT ( [Date], "MMM" ),   -- deutsch, wenn Modell-Locale de-DE
            "Kalenderwoche", WEEKNUM ( [Date], 2 ),
            "Wochentag", FORMAT ( [Date], "ddd" )        -- deutsch, wenn Modell-Locale de-DE
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

Die Tabelle **`daten/kalender_tagesbasis.csv`** (374 Zeilen, 2025-10-24 → 2026-11-01,
erzeugt von `daten/build_kalender_tagesbasis.py`) hat **eine Zeile pro Tag** und deckt
exakt denselben Zeitraum wie die `kalender`-Tabelle ab – sie lässt sich also
**1:1 über `Datum` zusammenführen**:

| Spalte | Inhalt |
| --- | --- |
| `Datum` | Tagesdatum |
| `Jahr` / `Quartal` / `Monat` / `Monatsname` / `Kalenderwoche` / `Wochentag` | Zeitattribute (deutsch: `Oktober`, `Donnerstag`) |
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
| gesamt | 176 | 204 | **86,3 %** |
| Phase 1 (24.10.–13.12.2025) | 35 | 51 | **68,6 %** |
| Phase 2 (Mai–Okt 2026) | 141 | 153 | **92,2 %** |
| Okt 2025 (ab 24.) | 3 | 8 | 37,5 % |
| Nov 2025 | 27 | 30 | 90,0 % |
| Dez 2025 (bis 13.) | 5 | 13 | 38,5 % |
| Mai 2026 (ab 22.) | 9 | 10 | 90,0 % |
| Jun 2026 | 25 | 30 | 83,3 % |
| Jul 2026 | 28 | 31 | 90,3 % |
| Aug 2026 (abzgl. 10 gesperrt) | 21 | 21 | **100,0 %** |
| Sep 2026 | 28 | 30 | 93,3 % |
| Okt 2026 | 30 | 31 | **96,8 %** |

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
        { "Phase 2 (Mai-Okt 2026)", DATE ( 2026, 5, 22 ), DATE ( 2026, 10, 31 ) }
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
    - IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Okt 2026)", 10, 0 )
```

```dax
-- Gesperrte Nächte (Eigennutzung/Instandhaltung) sind NICHT verfügbar.
-- Phase 2: 07.–16.08.2026 = 10 Nächte. Ohne diesen Abzug wäre die
-- Auslastung von Phase 2 fälschlich 86,5 % statt 92,2 %.
--
-- ⚠️ Phasenfalle: eine eigenständige Measure OHNE Phasenbezug liefert in JEDER
-- Zeile 10 – auch in Phase 1 (Okt–Dez 2025), wo nichts gesperrt ist. Phase 1
-- wäre dann 35/41 = 85,4 % statt korrekt 35/51 = 68,6 %. Deshalb phasengebunden:
Gesperrte Naechte =
    IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Okt 2026)", 10, 0 )

-- Saubere Dauerlösung (statt der festen 10): eigene Tabelle `sperrzeiten` mit
-- Betriebsphase-Spalte + Beziehung betriebsphasen[Betriebsphase] (1) →
-- sperrzeiten[Betriebsphase] (*). Dann ist die Sperre automatisch phasengebunden:
--
--   sperrzeiten = DATATABLE ( "Betriebsphase", STRING, "Ab", DATETIME, "Bis", DATETIME,
--       { { "Phase 2 (Mai-Okt 2026)", DATE ( 2026, 8, 7 ), DATE ( 2026, 8, 16 ) } } )
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
        - IF ( SELECTEDVALUE ( betriebsphasen[Betriebsphase] ) = "Phase 2 (Mai-Okt 2026)", 10, 0 )
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

**Verifizierte Werte** (aus `buchungen.csv`, 53 Zeilen nachgerechnet):

| Betriebsphase | Belegt | Verfügbar | Auslastung |
| --- | --- | --- | --- |
| Phase 1 (24.10.–13.12.2025) | 35 | 51 | **68,6 %** |
| Phase 2 (Mai–Okt 2026) | 141 | 153 | **92,2 %** |
| beide ausgewählt | 176 | 204 | 86,3 % |
| keine Auswahl (inkl. Phase 0) | 176 | 287 | 61,3 % — **bedeutungslos** |

Das Buchungsfenster von Phase 2 reicht jetzt bis 31.10.2026 – der Überhang von **B001**
(Anreise 28.09.2026, Abreise 03.10.2026) liegt damit vollständig im Fenster, die
buchungsbasierte und die tageweise Zählung ergeben beide 141 Nächte. Die Report-Zahl
**92,2 %** ist die phasengenaue.

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
VAR Phase = "Phase 2 (Mai-Okt 2026)"
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

Werte: **Auslastung % Phase 1 = 68,6 %** (35/51) · **Auslastung % Phase 2 = 92,2 %** (141/153).

> Nebenwirkung: Beide Measures sind konstant – der Betriebsphasen-Slicer hat auf sie
> **keinen** Einfluss mehr. Wenn der Slicer die Quoten steuern soll, statt der festen
> Variante `Auslastung % je Phase` oben verwenden.

**Ein Measure für beide Phasen.** Statt zwei fester Measures eines, das die Phase aus
**Slicer bzw. Matrix-Zeile** liest. Damit zeigt eine Card je nach Slicer 68,6 % oder
92,2 %, eine Matrix mit `betriebsphasen[Betriebsphase]` auf den Zeilen beide Werte.
Die gesperrten Nächte kommen aus der Spalte `Gesperrte_Naechte` – die harte `-10`
entfällt, das Measure bleibt auch bei künftigen Sperrungen korrekt:

```dax
Auslastung % Phase =
VAR Phase = SELECTEDVALUE ( betriebsphasen[Betriebsphase] )
VAR Ab =
    CALCULATE ( MIN ( betriebsphasen[Verfuegbar_ab] ), betriebsphasen[Betriebsphase] = Phase )
VAR Bis =
    CALCULATE ( MAX ( betriebsphasen[Verfuegbar_bis] ), betriebsphasen[Betriebsphase] = Phase )
VAR Gesperrt =
    CALCULATE ( MAX ( betriebsphasen[Gesperrte_Naechte] ), betriebsphasen[Betriebsphase] = Phase )
VAR Verfuegbar = ( Bis - Ab ) + 1 - Gesperrt
VAR Belegt =
    SUMX (
        FILTER ( buchungen, buchungen[Betriebsphase] = Phase && buchungen[Naechte_Belegt] > 0 ),
        MAX ( 0, MIN ( buchungen[Abreise], Bis + 1 ) - MAX ( buchungen[Anreise], Ab ) )
    )
RETURN
    DIVIDE ( Belegt, Verfuegbar )
```

Ergebnis: **Phase 1 = 68,6 %** (35/51) · **Phase 2 = 92,2 %** (141/153).

> Achtung Total: Ohne genau **eine** gewählte Phase (Card ohne Slicer, Zeile
> „Gesamt" in der Matrix) liefert `SELECTEDVALUE` leer → `DIVIDE` leer. Für die
> Gesamtquote (86,3 %) die Variante unten nehmen.

**Gesamtquote über beide Phasen (176/204 = 86,3 %).** Iteriert die Phasen und
summiert Belegt und Verfügbar – funktioniert in Card wie Matrix:

```dax
Auslastung % beide Phasen =
VAR Belegt =
    SUMX (
        VALUES ( betriebsphasen[Betriebsphase] ),
        VAR Phase = betriebsphasen[Betriebsphase]
        VAR Ab = CALCULATE ( MIN ( betriebsphasen[Verfuegbar_ab] ), betriebsphasen[Betriebsphase] = Phase )
        VAR Bis = CALCULATE ( MAX ( betriebsphasen[Verfuegbar_bis] ), betriebsphasen[Betriebsphase] = Phase )
        RETURN
            SUMX (
                FILTER ( buchungen, buchungen[Betriebsphase] = Phase && buchungen[Naechte_Belegt] > 0 ),
                MAX ( 0, MIN ( buchungen[Abreise], Bis + 1 ) - MAX ( buchungen[Anreise], Ab ) )
            )
    )
VAR Verfuegbar =
    SUMX (
        VALUES ( betriebsphasen[Betriebsphase] ),
        VAR Phase = betriebsphasen[Betriebsphase]
        VAR Ab = CALCULATE ( MIN ( betriebsphasen[Verfuegbar_ab] ), betriebsphasen[Betriebsphase] = Phase )
        VAR Bis = CALCULATE ( MAX ( betriebsphasen[Verfuegbar_bis] ), betriebsphasen[Betriebsphase] = Phase )
        VAR G = CALCULATE ( MAX ( betriebsphasen[Gesperrte_Naechte] ), betriebsphasen[Betriebsphase] = Phase )
        RETURN ( Bis - Ab ) + 1 - G
    )
RETURN
    DIVIDE ( Belegt, Verfuegbar )
```

Werte: **Gesamt = 86,3 %** (176/204). In einer Matrix mit `Betriebsphase` auf den
Zeilen liefert sie je Zeile 68,6 % / 92,2 % und in der Gesamtzeile 86,3 %.

```dax
ADR Netto = DIVIDE ( [Umsatz Netto], [Belegte Naechte] )
```

### ADR je Phase („ADR pro Periode") – braucht KEINE neue Measure

`ADR Netto` rechnet im **aktuellen Filterkontext**. Sobald `Betriebsphase` im Visual
liegt (Matrix-Zeilen oder Slicer), liefert dieselbe Measure den Phasenwert.

| Kontext | Umsatz netto | Belegte Nächte | ADR netto |
| --- | --- | --- | --- |
| gesamt | 10.172,85 € | 176 | **57,80 €** |
| Phase 1 (Okt–Dez 2025) | 1.984,81 € | 35 | **56,71 €** |
| Phase 2 (Mai–Okt 2026) | 8.188,04 € | 141 | **58,07 €** |

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
        buchungen[Betriebsphase] = "Phase 2 (Mai-Okt 2026)"
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
        buchungen[Betriebsphase] = "Phase 2 (Mai-Okt 2026)"
    )
```

**Drei Fallen**

1. **Nie `AVERAGE ( buchungen[ADR_Netto] )`.** Die Spalte ist der ADR *je Buchung*; der
   ungewichtete Mittelwert zählt kurze Aufenthalte gleich viel wie lange → Phase 2
   **57,18 €** statt 58,07 €. Richtig ist immer
   `Umsatz ÷ Nächte` (gewichtet).
2. **Storno zählt zum Umsatz, nicht zur Belegung.** B003 (127,43 €, 0 belegte Nächte)
   hebt den ADR von Phase 2 um +0,90 € (57,17 → 58,07). Bewusst so – das Geld ist real.
3. **Nenner ist die Belegung (`Naechte_Belegt`), nicht `Naechte`.** Sonst zählt B037
   (Verlängerung, 0 belegte Nächte) doppelt: 8.188,04 / 149 = 54,95 € statt 58,07 €.

Zähler und Nenner sind hier beide **buchungsbasiert** (Phase über die Anreise) und damit
in sich stimmig. Die *Auslastung* rechnet dagegen **tageweise** – seit der Verlängerung
des Fensters bis 31.10.2026 ergeben beide Zählungen für Phase 2 **141** Nächte, die
Kennzahlen stimmen also exakt überein (früher ragte B001 mit 2 Nächten über den
30.09. hinaus, die Auslastung zählte 111 statt 113).

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

Für zwei Karten nebeneinander („Auslastung 68,6 % → 92,2 %", „ADR 56,71 € → 58,07 €").
Beide Maßzahlen sind **fest verdrahtet** – jede Phase wird per `CALCULATE` selbst gesetzt,
also zeigen sie in jeder Visualisierung denselben Wert und ignorieren Slicer.

Einfachste Fassung – nur möglich, wenn die beiden Phasen-Maßzahlen schon existieren
(`Auslastung % Phase 1` / `Auslastung % Phase 2`, die 68,6 % und 92,2 % zeigen):

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
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 2 (Mai-Okt 2026)" )
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
        buchungen[Betriebsphase] = "Phase 2 (Mai-Okt 2026)"
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
    CALCULATE ( [Auslastung %], kalender[Betriebsphase] = "Phase 2 (Mai-Okt 2026)" )
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
        buchungen[Betriebsphase] = "Phase 2 (Mai-Okt 2026)"
    )
RETURN
    DIVIDE ( P2, P1 ) - 1
```

Sollwerte:

| Maßzahl | Ergebnis |
| --- | --- |
| `Auslastung % Differenz P2-P1` | **+23,5 Pp** (0,235) |
| `Auslastung % Veraenderung P2-P1` | **+34,3 %** |
| `ADR Differenz P2-P1` | **+1,36 €** |
| `ADR Veraenderung P2-P1` | **+2,4 %** |

**Fallen**

1. **Prozentpunkt ≠ Prozent.** Die Auslastungs-Differenz ist 0,235 – als Prozent formatiert
   steht dort „22,4 %". Wer das als relative Steigerung liest, liegt um Faktor 1,5 daneben
   (richtig: +34,3 %). Für eindeutige Beschriftung ein benutzerdefiniertes Format setzen:
   `+0,0" Pp";-0,0" Pp"`.
2. **Die ADR-Differenz nie über `AVERAGE ( buchungen[ADR_Netto] )` bilden** – ungewichtet
   ergibt das 59,19 € / 57,18 € und damit **−2,01 €** statt der richtigen **+1,36 €**.
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

Ergebnis: `▲ 23,5 Pp` in Grün bzw. `▲ 1,36 €` in Grün – bei negativer Entwicklung
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
| 2 (Mai–Okt 2026) | Host-Only Fee | 15,5 % + MwSt. = **18,45 %** | 0 % – im Preis enthalten |

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
Tatsächlich gestiegen: **+21,1 %** (58,81 € → 71,21 € Listenpreis je Nacht). Die
Auszahlung je Nacht blieb dadurch praktisch konstant (56,71 € → 58,07 €). Die
Erhöhung war also **richtig bemessen** (mit etwas Luft): sie kompensiert die
Gebühr und hält den Netto-Preis stabil.

```dax
Listenpreis je Nacht = DIVIDE ( [Umsatz Brutto], [Belegte Naechte] )
```

**Der Multiplikator-Effekt.** Jede künftige Netto-Erhöhung um 1 € verlangt jetzt
eine Listenpreis-Erhöhung von `1 / 0,8155 = 1,23 €`. Vor der Umstellung waren es
`1 / 0,9643 = 1,04 €`. Der Preisspielraum ist damit strukturell enger geworden –
ein Nachteil des Host-Only-Modells, unabhängig von der Auslastung.

---

## 8. Preis-Simulator (What-if) – Seite „Preis testen"

**Zweck:** Preis ändern und sehen, was passiert. **Wichtig vorab:** In den Daten
steckt **keine** Preiselastizität. Modell B (`analyse/buchungstreiber.py`) erklärt den
*erzielten* Preis je Nacht – nicht, wie die Nachfrage auf eine Preisänderung reagiert.
Die Seite trennt daher sauber:

- **Block 1 – reine Preiswirkung** (belastbar): Umsatz bei **konstanter Auslastung**.
  Das ist die *Obergrenze* – sie gilt nur, wenn die Nachfrage nicht wegbricht.
- **Block 2 – Break-even** (belastbar): Wie viel Nachfrage darf ich verlieren, damit der
  Umsatz gleich bleibt? Das ist die eigentliche Entscheidungsgröße.
- **Block 3 – mit Elastizität** (Annahme): Ein Regler für die Nachfragereaktion. Nur als
  „was wäre wenn", **nie** als Ergebnis verkaufen.

### 8.1 Der Parameter

Modellierung → **Neuer Parameter** → *Numerischer Bereich*:

| Feld | Wert |
| --- | --- |
| Name | `Preisänderung %` |
| Minimum | `-0.30` |
| Maximum | `0.30` |
| Schrittweite | `0.05` |
| Standard | `0` |

Power BI legt die Tabelle `Preisänderung %` mit Spalte `Preisänderung %` und Measure
`Preisänderung % Wert` an. Beide Namen exakt so lassen.

### 8.2 Basismaßzahlen (falls nicht vorhanden)

```dax
ADR Netto = DIVIDE ( [Umsatz Netto], [Belegte Naechte] )
```
```dax
Verfuegbare Naechte = SUM ( betriebsphasen[Verfuegbare_Naechte] )
```

> `Verfuegbare Naechte` hier bewusst aus `betriebsphasen[Verfuegbare_Naechte]` (204 gesamt,
> 51 / 153 je Phase) – die fertige Spalte, nicht die gerechnete Maßzahl. So stimmt der
> Nenner auch ohne Phasenfilter.

### 8.3 Block 1 – reine Preiswirkung (Auslastung konstant)

```dax
Simulierter ADR =
    [ADR Netto] * ( 1 + [Preisänderung % Wert] )
```
```dax
Simulierter Umsatz =
    [Belegte Naechte] * [Simulierter ADR]
```
```dax
Umsatz Delta = [Simulierter Umsatz] - [Umsatz Netto]
```
```dax
Umsatz Delta % = DIVIDE ( [Umsatz Delta], [Umsatz Netto] )
```

### 8.4 Block 2 – Break-even (die Entscheidungsgröße)

```dax
Break-even Naechte =
    DIVIDE ( [Umsatz Netto], [Simulierter ADR] )
```
```dax
Break-even Auslastung % =
    DIVIDE ( [Break-even Naechte], [Verfuegbare Naechte] )
```
```dax
Erforderliche Nachfrage % =
    DIVIDE ( [Break-even Naechte] - [Belegte Naechte], [Belegte Naechte] )
```

**Lesart von `Erforderliche Nachfrage %`:** negativ = *so viel Nachfrage darf ich
verlieren*; positiv = *so viel bräuchte ich zusätzlich*. Bei +10 % Preis sind das
**−9,1 %** → bricht die Nachfrage um mehr als 9 % ein, ist die Erhöhung ein Verlust.

### 8.5 Block 3 – mit Elastizität (ANNAHME, klar kennzeichnen)

Zweiter Parameter, gleiche Technik:

| Feld | Wert |
| --- | --- |
| Name | `Nachfrage-Elastizitaet` |
| Minimum | `-2` |
| Maximum | `0` |
| Schrittweite | `0.1` |
| Standard | `0` |

```dax
Simulierte Naechte =
    [Belegte Naechte] * ( 1 + [Nachfrage-Elastizitaet Wert] * [Preisänderung % Wert] )
```
```dax
Umsatz mit Elastizitaet =
    [Simulierte Naechte] * [Simulierter ADR]
```

> **Ehrlichkeitshinweis auf die Seite schreiben:** „Elastizität = −1" bedeutet: 10 %
> Preiserhöhung → 10 % weniger Nächte. Dieser Wert ist **gesetzt, nicht gemessen** –
> unsere 52 Buchungen reichen für keine belastbare Schätzung. Der Block zeigt die
> Mechanik, nicht die Wahrheit.

### 8.6 Referenzwerte (gerechnet, `analyse/preisszenario.py`)

Gesamtbasis: Umsatz **10.172,85 €**, **176** belegte Nächte, ADR **57,80 €**, 204 verfügbar.

| Preis-Δ | Preis | Umsatz (Auslastung konstant) | Break-even-Nächte | Break-even-Auslastung | darf verlieren |
| --- | --- | --- | --- | --- | --- |
| −20 % | 46,24 € | 8.138,28 € | 220,0 | 107,8 % | +25,0 % |
| −10 % | 52,02 € | 9.155,57 € | 195,6 | 95,9 % | +11,1 % |
| **0 %** | **57,80 €** | **10.172,85 €** | **176,0** | **86,3 %** | **0 %** |
| +10 % | 63,58 € | 11.190,14 € | 160,0 | 78,4 % | −9,1 % |
| +20 % | 69,36 € | 12.207,42 € | 146,7 | 71,9 % | −16,7 % |
| +30 % | 75,14 € | 13.224,71 € | 135,4 | 66,4 % | −23,1 % |

> **Sofort lesbar:** Eine Preiserhöhung lohnt erst, wenn die Nachfrage *weniger* stark
> einbricht als der Break-even-Wert. Bei +10 % liegt die Latte bei 9,1 % Nachfrageverlust.
> Bei −10 % Preis bräuchte ich **+11,1 % mehr Nächte** – mehr als die 28 unbesetzten
> buchbaren Tage hergeben (16,0 % der 176). Eine reine Preissenkung kann das Loch also
> nur über neue Nachfrage schließen, nicht über den bestehenden Kalender.

### 8.7 Seitenaufbau (Vorschlag)

| Bereich | Inhalt |
| --- | --- |
| Oben links | Slicer **`Preisänderung %`** (Kachel-Optik, „Testpreis" in € anzeigen) |
| Oben Mitte | Cards: `Simulierter ADR` · `Simulierter Umsatz` · `Umsatz Delta` · `Umsatz Delta %` |
| Oben rechts | Card `Break-even Auslastung %` mit bedingter Farbe (grün, wenn unter Ist-Auslastung) |
| Mitte | Liniendiagramm: X = `Preisänderung %`-Werte, Y = `Simulierter Umsatz` + `Umsatz Netto` als Referenzlinie |
| Unten | Tabelle: die Referenzwerte aus 8.6 als geladene Tabelle `preisszenarien_gesamt.csv` |
| Fußzeile | Der Ehrlichkeitshinweis aus 8.5, klein, grau |

**Bedingte Farbe für die Break-even-Card:**

```dax
Break-even Farbe =
    VAR Ist = DIVIDE ( [Belegte Naechte], [Verfuegbare Naechte] )
    RETURN IF ( [Break-even Auslastung %] <= Ist, "#2E7D32", "#C62828" )
```
