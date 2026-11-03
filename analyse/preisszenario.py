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

Ausgabeformat (Festlegung Chris, 20.10.2026): deutsche Schreibweise -
Semikolon als Trennzeichen, Dezimalkomma, UTF-8 mit BOM. Sonst liest ein
deutsches Power BI den Punkt als Tausenderpunkt und macht aus 40,46 -> 4046.
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

# Spalten der Tabelle (einheitlich fuer CSV und XLSX-Blatt)
KOPF = ['Basis', 'Preis_Delta_Pct', 'Preis_je_Nacht_EUR', 'Umsatz_Konstant_EUR',
        'Umsatz_Delta_EUR', 'Umsatz_Delta_Pct', 'Break_even_Naechte',
        'Break_even_Auslastung_Pct', 'Erforderliche_Nachfrageaenderung_Pct']


def lade_buchungen():
    # Deutsche Schreibweise: Semikolon-Trenner, Dezimalkomma.
    with open(os.path.join(DATEN, 'buchungen.csv'), encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh, delimiter=';'))


def zahl_de(s):
    """Deutsche Zahl (Dezimalkomma) -> float."""
    s = (s or '').strip()
    return float(s.replace('.', '').replace(',', '.')) if s else 0.0


def summe(rows):
    umsatz = sum(zahl_de(b['Netto_Betrag']) for b in rows)
    naechte = sum(int(zahl_de(b['Naechte_Belegt'])) for b in rows)
    return umsatz, naechte


def szenarien(basis_name, umsatz, naechte, verfuegbar):
    """Liste von Zeilen (numerische Werte) fuer eine Basis.

    Prozentwerte als Prozentpunkte (z. B. -30.0 fuer -30 %), nicht als
    Bruchteil - so sind sie in Power BI direkt lesbar.
    """
    basis = umsatz / naechte
    zeilen = []
    for dp in SCHRITTE:
        preis = basis * (1 + dp)
        umsatz_k = naechte * preis
        be = umsatz / preis
        zeilen.append([
            basis_name,
            round(dp * 100, 2),
            round(preis, 2),
            round(umsatz_k, 2),
            round(umsatz_k - umsatz, 2),
            round((umsatz_k - umsatz) / umsatz * 100, 2),
            round(be, 1),
            round(be / verfuegbar * 100, 2),
            round((be - naechte) / naechte * 100, 2),
        ])
    return zeilen


def alle_szenarien():
    """Alle Zeilen (gesamt + je Phase) fuer das XLSX-Blatt. (KOPF, rows)."""
    buchungen = lade_buchungen()
    rows = []
    for name, verf in VERFUEGBAR.items():
        if name == 'gesamt':
            rows += szenarien('gesamt', *summe(buchungen), verf)
        else:
            rows += szenarien(name, *summe([b for b in buchungen if b['Betriebsphase'] == name]), verf)
    return KOPF, rows


def _de(x, dec=2):
    """Zahl -> deutsche Schreibweise (Dezimalkomma)."""
    return f'{x:.{dec}f}'.replace('.', ',')


def _kurz(name):
    return 'gesamt' if name == 'gesamt' else 'phase' + name.split()[1]


def main():
    buchungen = lade_buchungen()
    os.makedirs(OUT, exist_ok=True)
    for name, verf in VERFUEGBAR.items():
        rows = buchungen if name == 'gesamt' else [b for b in buchungen if b['Betriebsphase'] == name]
        umsatz, naechte = summe(rows)
        zeilen = szenarien(name, umsatz, naechte, verf)

        ziel = os.path.join(OUT, f'preisszenarien_{_kurz(name)}.csv')
        with open(ziel, 'w', encoding='utf-8-sig', newline='') as fh:
            w = csv.writer(fh, delimiter=';', lineterminator='\n')
            w.writerow(KOPF)
            for z in zeilen:
                w.writerow([z[0], _de(z[1]), _de(z[2]), _de(z[3]), _de(z[4]),
                            _de(z[5]), _de(z[6], 1), _de(z[7]), _de(z[8])])

        print(f'\n=== {name} ===')
        print(f'Basis: Umsatz {umsatz:.2f} EUR | Naechte {naechte} | '
              f'ADR {umsatz / naechte:.2f} EUR | verfuegbar {verf}')
        print(f'{"dP":>6} {"Preis":>7} {"Umsatz":>10} {"Delta":>9} '
              f'{"Delta%":>7} {"BE-Naechte":>10} {"BE-Ausl":>7} {"erf.Nachfr.":>11}')
        for z in zeilen:
            print(f'{z[1]:>+6.0f} {z[2]:>7.2f} {z[3]:>10.2f} {z[4]:>+9.2f} '
                  f'{z[5]:>+7.1f} {z[6]:>10.1f} {z[7]:>7.1f} {z[8]:>+11.1f}')

    print('\nHinweis: "Umsatz" haelt die Auslastung KONSTANT - reine Preiswirkung.')
    print('"erf.Nachfr." = noetige Nachfrageaenderung fuer den Break-even:')
    print('negativ = so viel darf ich verlieren, positiv = so viel brauche ich.')
    print('CSV-Format: Semikolon, Dezimalkomma, UTF-8 BOM (deutsche Schreibweise).')


if __name__ == '__main__':
    main()
