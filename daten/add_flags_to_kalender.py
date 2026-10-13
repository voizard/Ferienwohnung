#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Erweitert kalender.csv um Betriebsphase, Verfuegbar und Belegt.

Quelle der beiden Flags und der Phasenzuordnung ist kalender_tagesbasis.csv
(erzeugt von build_kalender_tagesbasis.py). kalender.csv behaelt seine
7 Spalten und bekommt drei dazu -> Drop-in fuer das Power-BI-Modell,
Der Host muss nur aktualisieren.

Ergebnis: kalender.csv mit 10 Spalten, 345 Zeilen (2025-10-24 .. 2026-10-03).
"""
import csv
import os

OUT = os.path.dirname(os.path.abspath(__file__))
ZIEL = os.path.join(OUT, 'kalender.csv')
QUELLE = os.path.join(OUT, 'kalender_tagesbasis.csv')
NEUE_SPALTEN = ['Betriebsphase', 'Verfuegbar', 'Belegt']


def main():
    quelle = {r['Datum']: r for r in csv.DictReader(open(QUELLE, encoding='utf-8-sig'))}
    with open(ZIEL, encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))

    fehlend = [r['Datum'] for r in rows if r['Datum'] not in quelle]
    if fehlend:
        raise SystemExit(f'Diese Daten fehlen in {QUELLE}: {fehlend}')

    kopf = list(rows[0].keys())
    for s in NEUE_SPALTEN:
        if s in kopf:
            kopf.remove(s)
    kopf += NEUE_SPALTEN

    with open(ZIEL, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=kopf)
        w.writeheader()
        for r in rows:
            q = quelle[r['Datum']]
            for s in NEUE_SPALTEN:
                r[s] = q[s]
            w.writerow(r)

    verf = sum(1 for r in rows if r['Verfuegbar'] == 'ja')
    bel = sum(1 for r in rows if r['Belegt'] == 'ja')
    print(f'kalender.csv: {len(rows)} Zeilen, {len(kopf)} Spalten')
    print(f'  Verfuegbar ja = {verf} | Belegt ja = {bel} -> {bel / verf * 100:.1f} %')
    for ph in dict.fromkeys(r['Betriebsphase'] for r in rows):
        v = sum(1 for r in rows if r['Betriebsphase'] == ph and r['Verfuegbar'] == 'ja')
        b = sum(1 for r in rows if r['Betriebsphase'] == ph and r['Belegt'] == 'ja')
        pct = f'{b / v * 100:.1f} %' if v else '—'
        print(f'  {ph}: {b}/{v} = {pct}')


if __name__ == '__main__':
    main()
