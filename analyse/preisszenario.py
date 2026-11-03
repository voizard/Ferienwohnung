#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Preis-Szenarien fuer die Power-BI-Seite "Preis-Simulator".

Ehrlichkeitsprinzip: Es gibt KEINE aus den Daten geschaetzte
Preiselastizitaet. Modell B (analyse/buchungstreiber.py) erklaert den
ERZIELTEN Preis je Nacht - nicht, wie die Nachfrage auf eine Preisaenderung
reagiert. Dieses Skript rechnet deshalb nur zwei belastbare Groessen:

  1. Umsatz bei KONSTANTER Auslastung - reine Preiswirkung (Obergrenze).
  2. Break-even-Naechte - wie viel Nachfrage darf ich verlieren, damit der
     Umsatz trotzdem gleich bleibt.

Eine Nachfragereaktion mit Elastizitaet ist eine ANNAHME und wird hier
bewusst nicht als Ergebnis ausgegeben.
"""
import csv
import os

HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(os.path.dirname(HIER), 'daten')
OUT = os.path.join(HIER, 'out')

VERFUEGBAR = {
    'gesamt': 204,
    'Phase 1 (Okt-Dez 2025)': 51,
    'Phase 2 (Mai-Okt 2026)': 153,
}
SCHRITTE = [x / 100 for x in range(-30, 31, 5)]


def lade_buchungen():
    with open(os.path.join(DATEN, 'buchungen.csv'), encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh))


def summe(rows):
    umsatz = sum(float(b['Netto_Betrag']) for b in rows)
    naechte = sum(int(b['Naechte_Belegt']) for b in rows)
    return umsatz, naechte


def szenarien(umsatz, naechte, verfuegbar):
    basis = umsatz / naechte
    zeilen = []
    for dp in SCHRITTE:
        preis = basis * (1 + dp)
        umsatz_k = naechte * preis
        be = umsatz / preis
        zeilen.append({
            'dp_pct': f'{dp * 100:+.0f} %',
            'preis_je_nacht': round(preis, 2),
            'umsatz_konstant': round(umsatz_k, 2),
            'delta_eur': round(umsatz_k - umsatz, 2),
            'delta_pct': f'{(umsatz_k - umsatz) / umsatz * 100:+.1f} %',
            'be_naechte': round(be, 1),
            'be_auslastung': f'{be / verfuegbar * 100:.1f} %',
            'erf_nachfrage': f'{(be - naechte) / naechte * 100:+.1f} %',
        })
    return zeilen


def main():
    buchungen = lade_buchungen()
    gruppen = {'gesamt': buchungen}
    for ph in VERFUEGBAR:
        if ph != 'gesamt':
            gruppen[ph] = [b for b in buchungen if b['Betriebsphase'] == ph]

    os.makedirs(OUT, exist_ok=True)
    for name, rows in gruppen.items():
        umsatz, naechte = summe(rows)
        zeilen = szenarien(umsatz, naechte, VERFUEGBAR[name])
        kurz = 'gesamt' if name == 'gesamt' else 'phase' + name.split()[1]
        ziel = os.path.join(OUT, f'preisszenarien_{kurz}.csv')
        with open(ziel, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(zeilen[0].keys()))
            w.writeheader()
            w.writerows(zeilen)
        print(f'\n=== {name} ===')
        print(f'Basis: Umsatz {umsatz:.2f} EUR | Naechte {naechte} | '
              f'ADR {umsatz / naechte:.2f} EUR | verfuegbar {VERFUEGBAR[name]}')
        print(f'{"dP":>6} {"Preis":>7} {"Umsatz":>10} {"Delta":>9} '
              f'{"Delta%":>7} {"BE-Naechte":>10} {"BE-Ausl":>7} {"erf.Nachfr.":>11}')
        for z in zeilen:
            print(f'{z["dp_pct"]:>6} {z["preis_je_nacht"]:>7.2f} '
                  f'{z["umsatz_konstant"]:>10.2f} {z["delta_eur"]:>+9.2f} '
                  f'{z["delta_pct"]:>7} {z["be_naechte"]:>10.1f} '
                  f'{z["be_auslastung"]:>7} {z["erf_nachfrage"]:>11}')

    print('\nHinweis: "Umsatz" haelt die Auslastung KONSTANT - reine Preiswirkung.')
    print('"erf.Nachfr." = noetige Nachfrageaenderung fuer den Break-even:')
    print('negativ = so viel darf ich verlieren, positiv = so viel brauche ich.')


if __name__ == '__main__':
    main()
