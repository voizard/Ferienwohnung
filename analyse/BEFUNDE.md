# Treiberanalyse: Belegung und Preis der Ferienwohnung

**Frage:** Was hängt damit zusammen, dass die Wohnung gebucht wird — und was
mit dem erzielten Nettopreis?

**Datenbasis:** `kalender.csv` (Tagespanel) und `buchungen.csv`
(Faktentabelle) aus `airbnb-portfolio/daten/`.
**Erzeugt von:** `analyse/buchungstreiber.py` — alle Zahlen hier sind
Skriptausgaben, keine Schätzungen aus dem Kopf.

---

## 1 · Auslastung: die Basis

| Kennzahl | Wert |
| --- | --- |
| Buchbare Tage (Nenner) | 204 |
| Davon belegt | 176 |
| Auslastung | **86,3 %** |
| Nicht belegte buchbare Tage | 28 |

Der Nenner enthält nur die Buchbarkeitsfenster der beiden Phasen — keine
Renovierungsmonate, keine gesperrten Nächte. Sonst wäre die Auslastung zu
niedrig.

### Nach Wochentag

| Wochentag | belegte Tage | buchbare Tage | Auslastung |
| --- | --- | --- | --- |
| Montag | 22 | 29 | 75,9 % |
| Dienstag | 24 | 29 | 82,8 % |
| Mittwoch | 25 | 29 | 86,2 % |
| Donnerstag | 24 | 29 | 82,8 % |
| Freitag | 29 | 30 | 96,7 % |
| Samstag | 29 | 30 | 96,7 % |
| Sonntag | 23 | 28 | 82,1 % |

Freitag und Samstag liegen bei 97 % bzw.
97 %, Montag und Donnerstag nur bei
76 % / 83 %.
Das ist der deutlichste Einzelunterschied im Datensatz.

### Nach Betriebsphase

| Betriebsphase | belegte Tage | buchbare Tage | Auslastung |
| --- | --- | --- | --- |
| Phase 1 (Okt-Dez 2025) | 35 | 51 | 68,6 % |
| Phase 2 (Mai-Okt 2026) | 141 | 153 | 92,2 % |

### Nach Monat

| Monat | belegte Tage | buchbare Tage | Auslastung |
| --- | --- | --- | --- |
| 2025-10 | 3 | 8 | 37,5 % |
| 2025-11 | 27 | 30 | 90,0 % |
| 2025-12 | 5 | 13 | 38,5 % |
| 2026-05 | 9 | 10 | 90,0 % |
| 2026-06 | 25 | 30 | 83,3 % |
| 2026-07 | 28 | 31 | 90,3 % |
| 2026-08 | 21 | 21 | 100,0 % |
| 2026-09 | 28 | 30 | 93,3 % |
| 2026-10 | 30 | 31 | 96,8 % |

⚠️ Die beiden Phasen sind **nicht** über denselben Kalender vergleichbar:
Phase 1 = Okt–Dez, Phase 2 = Mai–Okt. Der Phasenunterschied und der
Saisoneffekt sind in diesen Daten untrennbar.

## 2 · Wo die Lücken liegen

Alle 28 nicht belegten buchbaren Tage liegen **innerhalb**
des Vermietungszeitraums, keiner am Rand. Sie verteilen sich so:

| Monat | unbesetzte buchbare Tage |
| --- | --- |
| 2025-10 | 5 |
| 2025-11 | 3 |
| 2025-12 | 8 |
| 2026-05 | 1 |
| 2026-06 | 5 |
| 2026-07 | 3 |
| 2026-09 | 2 |
| 2026-10 | 1 |

Aufteilung nach Phase: **16** Tage in Phase 1 (von 51 = 
31,4 % unbesetzt), **12** Tage in Phase 2
(von 153 = 7,8 %).

In Phase 2 sind die Lücken **Einzeltage zwischen zwei Aufenthalten**, keine
Blöcke. Das passt zu Mindestaufenthalt und Reinigungsabstand: zwischen zwei
Aufenthalten bleibt ein Tag unverkäuflich, obwohl der Monat insgesamt stark
gebucht ist. Die Winterblöcke (Nov/Dez 2025) sind dagegen echte
Nachfragelücken.

**Praxis-Test:** Die 16 Wintertage sind der einzige echte Erlös-Hebel.
Verkauft man 5 der 16 Tage zu 55 € netto, sind das rund 275 € zusätzlich.
Die 12 Sommertage sind nur über eine Mindestaufenthalts-Anpassung zu holen.

## 3 · Modell A — Chance auf Belegung (Logit)

Zielgröße: `Belegt ja/nein` je buchbarem Tag (204 Tage).
Prädiktoren: Freitag/Samstag und Betriebsphase.
Standardfehler **geclustert nach Belegungsepisode**, weil aufeinanderfolgende
Nächte desselben Aufenthalts nicht unabhängig sind.

| Merkmal | Odds Ratio | 95%-KI | p-Wert |
| --- | --- | --- | --- |
| Freitag/Samstag | 7.79 | 1.37 – 44.32 | 0.021 |
| Betriebsphase 2 | 6.19 | 0.48 – 79.47 | 0.162 |

Lesart: Ein Odds Ratio von 7,8 heißt, dass ein Freitag oder
Samstag eine um den Faktor 7,8 höhere Chance hat, belegt zu
sein als ein Werktag — **6,79 ×** bzw. rund
679 % mehr.

**Warum geclustert:** ungeclustert wäre der Standardfehler für
„Freitag/Samstag" 0,77 statt
0,89. Der Wochenendeffekt ist also
weniger sicher als er naiv aussieht — das 95%-Intervall reicht von
1,4 bis 44,3.

Die Betriebsphase ist dagegen **nicht signifikant** (p = 0,162) —
ihr Effekt ist mit 28 nicht belegten Tagen nicht von
Zufall zu trennen.

**Nicht schätzbar:** Feiertage. Im buchbaren Fenster liegen nur
4 Feiertage (01.11.2025, 25.05.2026, 04.06.2026, 03.10.2026) —
zu wenige für einen eigenen Koeffizienten. Alle drei waren belegt.

## 4 · Modell B — Was den Nettopreis erklärt (OLS)

Buchungsebene, n = 52 (Storno ausgeschlossen: Umsatz ja, Aufenthalt
nein). Zielgröße: `ADR_Netto` = Nettopreis je Nacht.

| Merkmal | Effekt auf ADR | 95%-KI | p-Wert |
| --- | --- | --- | --- |
| Freitag/Samstag | -6,68 € | -14,42 – +1,05 € | 0,090 |
| Betriebsphase 2 | -7,93 € | -18,18 – +2,32 € | 0,130 |
| je zusätzliche Nacht | -2,02 € | -3,44 – -0,60 € | 0,005 |

R² = 0,275. Ohne die Verlängerungsbuchung (preislich ein Sonderfall):
R² = 0,240. n = 52 — mehr als drei Prädiktoren wären hier
unseriös.

Der klarste Effekt ist die **Aufenthaltsdauer**: längere Aufenthalte zahlen
je Nacht weniger. Der Wochentagseffekt beim *Preis* ist dagegen klein — der
Wochentag wirkt auf die **Wahrscheinlichkeit** einer Buchung, nicht auf den
Preis je Nacht.

## 5 · Was das praktisch heißt

- **Wochenenden tragen die Nachfrage.** Freitag/Samstag sind praktisch
  ausgebucht (97 % / 97 %).
  Wer Erlös steigern will, hebt den **Wochenendpreis**, nicht den Grundpreis.
- **Montag und Donnerstag sind die schwächsten Tage**
  (76 % / 83 %).
  Dort ist ein Rabatt oder eine Mindestaufenthaltslockerung wirksamer als
  eine allgemeine Preissenkung.
- **70 % der Buchungen sind ≤ 3 Nächte**, Median
  3,0 Nächte, medianer Vorlauf 16 Tage.
  Das ist Kurzfrist- und Kurzaufenthaltstourismus — Wochenendausflüge.
- **Der Preis je Nacht reagiert kaum auf den Wochentag**
  (-6,68 €, p = 0,09), sondern auf die
  **Aufenthaltsdauer**: jede zusätzliche Nacht kostet
  2,02 € weniger pro Nacht. Längere Aufenthalte werden also
  schon heute rabattiert.
- **Die Lücken liegen nicht in der Nachfrage, sondern im Kalender:**
  28 von 28 unbesetzten Tagen sitzen zwischen
  zwei Aufenthalten. Da ist der Hebel kleiner als er aussieht — ein Tag
  Zwischenlücke lässt sich kaum verkaufen.

## 6 · Grenzen — bitte mitlesen

1. **Korrelation, nicht Kausalität.** Der Preis ist selbst gesetzt, der
   Wochentag nicht. Nur der Wochentag ist hier exogen.
2. **Kleine Stichprobe.** 28 nicht belegte Tage tragen
   Modell A. Mehr als zwei Prädiktoren wären unseriös.
3. **Saison und Phase sind vermischt.** Phase 1 (Okt–Dez) und Phase 2
   (Mai–Okt) sind unterschiedliche Jahreszeiten; der Phaseneffekt enthält
   beides.
4. **Fehlende Nächte sind nicht sichtbar.** Sperren aus Eigennutzung oder
   Reparatur stehen nicht im Export — die Auslastung ist eine Obergrenze.
5. **Motive stehen hier nicht drin.** „Warum" jemand bucht, beantwortet
   keine Transaktion. Dafür bräuchte es Bewertungstexte
   (`daten/bewertungen_vorlage.csv`) oder eine Gästebefragung.
6. **Feiertage, Brückentage, Schulferien, Events** sind in dieser Fassung
   nicht als Prädiktoren enthalten — zu wenige Fälle bzw. keine belastbare
   Quelle im Workspace.
