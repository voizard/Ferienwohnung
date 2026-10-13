#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Baut die Tages-Tabelle (kalender_tagesbasis.csv) fuer das Power-BI-Modell.

Eine Zeile pro Tag. Damit sind Auslastung, Sperren und Ueberhaenge
automatisch korrekt - ein einziges Measure reicht:

    Auslastung % =
    DIVIDE (
        CALCULATE ( COUNTROWS ( kalender ), kalender[Belegt] = "ja" ),
        CALCULATE ( COUNTROWS ( kalender ), kalender[Verfuegbar] = "ja" )
    )

Logik:
  Verfuegbar = Tag liegt in einem Buchbarkeitsfenster UND ist nicht gesperrt
  Belegt     = ein Aufenthalt (ohne Storno) ueberdeckt den Tag
               -> Tageszählung = Vereinigung, Ueberlappungen zaehlen einmal
               -> Ueberhang ueber das Fensterende hinaus faellt automatisch raus
"""
import csv
import datetime
import os

OUT = os.path.dirname(os.path.abspath(__file__))

# Buchbarkeitsfenster (vom Host bestaetigt). Phase 0 (2020) ist ausgeschlossen.
# Phase 1 beginnt am 24.10.2025 - die Vermietung startete erst da (erste Buchung
# B044, Anreise 24.10.2025). Vorher war die Wohnung nicht buchbar.
# Phase 1 endet am 13.12.2025 (vom Host bestaetigt 2026-10-12): letzte Nacht war
# der 13.12., der 14.12.2025 ist nur der Abreisetag des letzten Gastes (B038).
# NICHT 31.12.2025 und nicht 14.12.2025.
PHASEN = [
    ('Phase 1 (Okt-Dez 2025)', datetime.date(2025, 10, 24), datetime.date(2025, 12, 13)),
    ('Phase 2 (Mai-Sep 2026)', datetime.date(2026, 5, 22), datetime.date(2026, 9, 30)),
]
# Gesperrt (Eigennutzung/Instandhaltung) - zaehlt NICHT als verfuegbar.
GESPERRT = [(datetime.date(2026, 8, 7), datetime.date(2026, 8, 16))]

START = min(p[1] for p in PHASEN)          # 2025-10-24
# ENDE bewusst bis 2026-10-03: identischer Zeitraum wie die alte kalender.csv
# (345 Zeilen) -> laesst sich 1:1 ueber 'Datum' zusammenfuehren.
ENDE = datetime.date(2026, 10, 3)
WOCHENTAG = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
MONATSNAME = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']


def phase_von(tag):
    for name, ab, bis in PHASEN:
        if ab <= tag <= bis:
            return name
    return 'Zwischenzeit (nicht buchbar)'


def ist_gesperrt(tag):
    return any(ab <= tag <= bis for ab, bis in GESPERRT)


def lade_belegte_tage():
    """Vereinigung aller Aufenthaltsnaechte, Storno ausgeschlossen."""
    pfad = os.path.join(OUT, 'buchungen.csv')
    tage = set()
    with open(pfad, encoding='utf-8-sig') as fh:
        for r in csv.DictReader(fh):
            if (r.get('Storno') or '').strip().lower() == 'ja':
                continue
            anreise = datetime.date.fromisoformat(r['Anreise'])
            abreise = datetime.date.fromisoformat(r['Abreise'])
            tag = anreise
            while tag < abreise:          # Abreisetag ist keine Nacht
                tage.add(tag)
                tag += datetime.timedelta(days=1)
    return tage


def main():
    belegt_tage = lade_belegte_tage()
    zeilen = []
    tag = START
    while tag <= ENDE:
        phase = phase_von(tag)
        verfuegbar = phase != 'Zwischenzeit (nicht buchbar)' and not ist_gesperrt(tag)
        zeilen.append({
            'Datum': tag.isoformat(),
            'Jahr': tag.year,
            'Quartal': (tag.month - 1) // 3 + 1,
            'Monat': tag.month,
            'Monatsname': MONATSNAME[tag.month - 1],
            'Kalenderwoche': tag.isocalendar()[1],
            'Wochentag': WOCHENTAG[tag.weekday()],
            'Betriebsphase': phase,
            'Verfuegbar': 'ja' if verfuegbar else 'nein',
            # Belegt = belegter Tag INNERHALB des Buchbarkeitsfensters.
            # Naechte ausserhalb (z. B. 01.-02.10.2026, Ueberhang von B001) zaehlen
            # bewusst nicht - sonst waere der Zaehler groesser als der Nenner.
            'Belegt': 'ja' if (verfuegbar and tag in belegt_tage) else 'nein',
        })
        tag += datetime.timedelta(days=1)

    ziel = os.path.join(OUT, 'kalender_tagesbasis.csv')
    with open(ziel, 'w', encoding='utf-8', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
        w.writeheader()
        w.writerows(zeilen)

    # Kontrolle
    verf = sum(1 for z in zeilen if z['Verfuegbar'] == 'ja')
    bel = sum(1 for z in zeilen if z['Belegt'] == 'ja')
    print(f'{len(zeilen)} Zeilen  {START} .. {ENDE}')
    print(f'Verfuegbar ja = {verf}   Belegt ja = {bel}   -> {bel / verf * 100:.1f} %')
    for name, ab, bis in PHASEN:
        v = [z for z in zeilen if z['Betriebsphase'] == name and z['Verfuegbar'] == 'ja']
        b = [z for z in v if z['Belegt'] == 'ja']
        print(f'  {name}: {len(b)}/{len(v)} = {len(b) / len(v) * 100:.1f} %')
    ausserhalb = [z for z in zeilen if z['Belegt'] == 'ja' and z['Verfuegbar'] == 'nein']
    print(f'  belegte Tage ausserhalb des Fensters: {len(ausserhalb)}')


if __name__ == '__main__':
    main()
