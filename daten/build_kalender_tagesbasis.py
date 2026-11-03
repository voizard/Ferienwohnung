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
import calendar
import collections
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
# Phase 2 lief ohne Unterbrechung in den Herbst hinein (vom Host bestaetigt
# 2026-11-02, Variante A: der Betrieb ging weiter, kein Saisonbruch). Ende =
# letzte belegte Nacht 31.10.2026; der 01.11.2026 ist nur Abreisetag.
PHASEN = [
    ('Phase 1 (Okt-Dez 2025)', datetime.date(2025, 10, 24), datetime.date(2025, 12, 13)),
    ('Phase 2 (Mai-Okt 2026)', datetime.date(2026, 5, 22), datetime.date(2026, 10, 31)),
]
# Gesperrt (Eigennutzung/Instandhaltung) - zaehlt NICHT als verfuegbar.
GESPERRT = [(datetime.date(2026, 8, 7), datetime.date(2026, 8, 16))]

START = min(p[1] for p in PHASEN)          # 2025-10-24
# ENDE = Abreisetag des letzten Aufenthalts (01.11.2026). Die letzte belegte
# Nacht ist der 31.10.2026; der 01.11. ist nur Abreisetag und traegt als Tag
# ausserhalb der Fenster 'Zwischenzeit (nicht buchbar)'.
ENDE = datetime.date(2026, 11, 1)
# Deutsche Namen - der Datensatz ist durchgaengig deutsch (Chris, 02.11.2026).
WOCHENTAG = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag']
MONATSNAME = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
              'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']


def phase_von(tag):
    for name, ab, bis in PHASEN:
        if ab <= tag <= bis:
            return name
    return 'Zwischenzeit (nicht buchbar)'


def ist_gesperrt(tag):
    return any(ab <= tag <= bis for ab, bis in GESPERRT)


def teilmonat_monate():
    """Monate, die NICHT vollstaendig im Buchbarkeitsfenster liegen.

    Ein Monat ist Teilmonat, wenn das Fenster ihn anschneidet (Fensterstart
    oder -ende faellt in den Monat). Beispiele: Okt 2025 (Start 24.10.),
    Dez 2025 (Ende 13.12.), Mai 2026 (Start 22.05.).

    Warum wichtig: Ein Teilmonat hat weniger verfuegbare Naechte, seine
    Auslastungsquote ist daher NICHT mit vollen Monaten vergleichbar. Im
    Monatsvergleich (Power BI) diese Monate kennzeichnen oder ausblenden -
    sonst liest man den Fensterausschnitt als Nachfrage (Chris, 03.11.2026).
    """
    im_fenster = collections.Counter()
    tag = START
    while tag <= ENDE:
        if phase_von(tag) != 'Zwischenzeit (nicht buchbar)':
            im_fenster[(tag.year, tag.month)] += 1
        tag += datetime.timedelta(days=1)
    teil = set()
    for (jahr, monat), tage in im_fenster.items():
        if tage < calendar.monthrange(jahr, monat)[1]:
            teil.add((jahr, monat))
    return teil


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
    teilmonate = teilmonat_monate()
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
            # Teilmonat = Monat wird vom Buchbarkeitsfenster angeschnitten.
            # Pro Tag konstant; im Monatsvergleich nicht mit vollen Monaten
            # vergleichen (siehe teilmonat_monate()).
            'Teilmonat': 'ja' if (tag.year, tag.month) in teilmonate else 'nein',
        })
        tag += datetime.timedelta(days=1)

    ziel = os.path.join(OUT, 'kalender_tagesbasis.csv')
    # utf-8-sig = mit BOM, wie kalender.csv/buchungen.csv (Chris' Vorgabe).
    with open(ziel, 'w', encoding='utf-8-sig', newline='') as fh:
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
    tm = sorted({(z['Jahr'], z['Monat']) for z in zeilen if z['Teilmonat'] == 'ja'})
    print(f'  Teilmonate (angeschnitten): {", ".join(f"{j}-{m:02d}" for j, m in tm)}')


if __name__ == '__main__':
    main()
