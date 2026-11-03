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
import calendar
import csv
import datetime
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
        'Break_even_Auslastung_Pct', 'Erforderliche_Nachfrageaenderung_Pct',
        'Ist_Auslastung_Pct', 'Ampel', 'Hinweis', 'Zeilenfarbe']

# Nachkommastellen je Spalte - fuer die deutsche CSV-Ausgabe.
# Zeilenfarbe = Hex-Farbe, mit der die Power-BI-Seite die Referenzzeile
# optisch hervorhebt (bedingte Formatierung "Feldwert" auf jeder Spalte).
DEZ = {
    'Preis_Delta_Pct': 2, 'Preis_je_Nacht_EUR': 2,
    'Umsatz_Konstant_EUR': 2, 'Umsatz_Delta_EUR': 2, 'Umsatz_Delta_Pct': 2,
    'Break_even_Naechte': 1, 'Break_even_Auslastung_Pct': 2,
    'Erforderliche_Nachfrageaenderung_Pct': 2, 'Ist_Auslastung_Pct': 2,
}
# Farbe der Referenzzeile (dezent grau) - Rest bleibt weiss/ohne Fuellung.
FARBE_REFERENZ = '#E8EEF4'

# Gleiche Rechnung, aber Basis = Monat ('YYYY-MM'). Vorne weg die Monats-
# Eckwerte, damit die Tabelle ohne Zusatzspalten lesbar ist.
#
# `Monat` ("Oktober 2025") + `Monat_Sort` (202510) sind fuer den Slicer da:
# Power BI erkennt "2025-10" beim Import automatisch als DATUM und zeigt im
# Slicer dann nur den Monatsersten (1. Oktober 2025 ...) - statt 9 Monaten.
# Deshalb im Slicer `Monat` verwenden und nach `Monat_Sort` sortieren.
KOPF_MONAT = (['Basis', 'Monat', 'Monat_Sort', 'Monat_Datum'] + KOPF[1:] +
              ['Belegte_Naechte', 'Verfuegbare_Naechte', 'Teilmonat'])

MONATSNAME = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
              'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember']


def monat_name(m):
    """'2025-10' -> 'Oktober 2025' (nicht als Datum lesbar)."""
    jahr, monat = int(m[:4]), int(m[5:7])
    return f'{MONATSNAME[monat - 1]} {jahr}'


def monat_sort(m):
    """'2025-10' -> 202510 (Sortierschluessel fuer Monat)."""
    return int(m[:4]) * 100 + int(m[5:7])


def monat_letzter_tag(m):
    """'2025-10' -> date(2025, 10, 31) - der LETZTE Tag des Monats.

    Besser als der Monatserste: Power BI beschriftet die Datumsachse dann
    mit "Oktober 2025" statt mit dem verwirrenden "1. Oktober".
    """
    jahr, monat = int(m[:4]), int(m[5:7])
    return datetime.date(jahr, monat, calendar.monthrange(jahr, monat)[1])


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
    ist = naechte / verfuegbar * 100          # Ist-Auslastung der Basis in %
    zeilen = []
    for dp in SCHRITTE:
        preis = basis * (1 + dp)
        umsatz_k = naechte * preis
        be = umsatz / preis
        be_ausl = be / verfuegbar * 100
        erf = (be - naechte) / naechte * 100
        # Ampel + Klartext direkt in die Daten - so braucht die Power-BI-Seite
        # kein DAX-Measure fuer Farbe und Beschriftung.
        #
        # Wichtig: die Break-even-Auslastung ist bei 100 % GEDECKELT - mehr
        # Naechte als verfuegbar gibt es nicht. Liegt der Break-even ueber den
        # verfuegbaren Naechten, ist die Preissenkung NICHT kompensierbar
        # (eigene Kategorie 'unmoeglich'), egal wie gut die Nachfrage waere.
        if abs(dp) < 0.0001:
            ampel, hinweis = 'referenz', 'Referenz (heutiger Preis)'
        elif be > verfuegbar:
            ampel = 'unmoeglich'
            frei = verfuegbar - naechte
            if frei <= 0:
                hinweis = 'unerreichbar - keine Nacht frei'
            elif frei == 1:
                hinweis = 'unerreichbar - nur 1 Nacht frei'
            else:
                hinweis = f'unerreichbar - nur {frei} Naechte frei'
        elif be_ausl <= ist:
            ampel = 'gruen'
            hinweis = f'darf {abs(erf):.1f} % verlieren'.replace('.', ',')
        else:
            ampel = 'rot'
            hinweis = f'braucht {erf:.1f} % mehr'.replace('.', ',')
        zeilen.append([
            basis_name,
            round(dp * 100, 2),
            round(preis, 2),
            round(umsatz_k, 2),
            round(umsatz_k - umsatz, 2),
            round((umsatz_k - umsatz) / umsatz * 100, 2),
            round(be, 1),
            round(be_ausl, 2),
            round(erf, 2),
            round(ist, 2),
            ampel,
            hinweis,
            # Treibt die bedingte Hintergrundfarbe der ganzen Zeile in
            # Power BI - nur die Referenzzeile bekommt eine Fuellung.
            FARBE_REFERENZ if ampel == 'referenz' else '',
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


def lade_kalender():
    with open(os.path.join(DATEN, 'kalender.csv'), encoding='utf-8-sig') as fh:
        return list(csv.DictReader(fh, delimiter=';'))


def monats_szenarien():
    """Gleiche Rechnung je Monat (Basis = 'YYYY-MM'). (KOPF_MONAT, rows).

    WICHTIG - Zuordnung auf TAGESBASIS, nicht nach Anreisemonat:
    Ein Aufenthalt wird dem Monat zugeordnet, in dem die Nacht LIEGT. Eine
    Buchung 28.09.-03.10. zaehlt also teils in den September, teils in den
    Oktober. Nach Anreisemonat gezaehlt bekaeme der Oktober nur die Naechte
    der Gaeste, die im Oktober angereist sind - die Auslastung waere zu
    niedrig (Okt 2026: 90,3 % statt richtig 96,8 %).

    Naechte + verfuegbare Naechte kommen aus kalender.csv (Tagesbasis), der
    Umsatz wird nach Kalendernaechten auf die Monate verteilt. Damit stimmt
    die Monatssumme der Auslastung mit der Gesamtauslastung ueberein
    (Summe belegte Tage / Summe verfuegbare Tage = 176/204 = 86,27 %).
    """
    buchungen = lade_buchungen()
    verfuegbar, belegt, teilmonat = {}, {}, {}
    for k in lade_kalender():
        m = k['Datum'][:7]
        if k.get('Verfuegbar') == 'ja':
            verfuegbar[m] = verfuegbar.get(m, 0) + 1
        if k.get('Belegt') == 'ja':
            belegt[m] = belegt.get(m, 0) + 1
        if k.get('Teilmonat') == 'ja':
            teilmonat[m] = 'ja'

    umsatz = {}
    for b in buchungen:
        von = datetime.date.fromisoformat(b['Anreise'])
        bis = datetime.date.fromisoformat(b['Abreise'])
        betrag = zahl_de(b['Netto_Betrag'])
        naechte = (bis - von).days
        if naechte <= 0:
            m = von.strftime('%Y-%m')
            umsatz[m] = umsatz.get(m, 0.0) + betrag
            continue
        tag = von
        while tag < bis:
            m = tag.strftime('%Y-%m')
            umsatz[m] = umsatz.get(m, 0.0) + betrag / naechte
            tag += datetime.timedelta(days=1)

    rows = []
    for m in sorted(verfuegbar):
        v = verfuegbar[m]
        n = belegt.get(m, 0)
        if v == 0 or n == 0:
            continue
        for z in szenarien(m, umsatz.get(m, 0.0), n, v):
            rows.append([z[0], monat_name(m), monat_sort(m),
                         monat_letzter_tag(m)] + z[1:] +
                        [n, v, teilmonat.get(m, 'nein')])
    return KOPF_MONAT, rows


def _de(x, dec=2):
    """Zahl -> deutsche Schreibweise (Dezimalkomma)."""
    return f'{x:.{dec}f}'.replace('.', ',')


def _csv_zeile(z, kopf):
    """Eine Zeile (numerische Werte) -> deutsche CSV-Werte, spaltenweise."""
    out = []
    for name, val in zip(kopf, z):
        if name in DEZ:
            out.append(_de(val, DEZ[name]))
        elif name in ('Belegte_Naechte', 'Verfuegbare_Naechte', 'Monat_Sort'):
            out.append(int(val))
        elif name == 'Monat_Datum' and hasattr(val, 'isoformat'):
            out.append(val.isoformat())
        else:
            out.append(val)
    return out


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
                w.writerow(_csv_zeile(z, KOPF))

        print(f'\n=== {name} ===')
        print(f'Basis: Umsatz {umsatz:.2f} EUR | Naechte {naechte} | '
              f'ADR {umsatz / naechte:.2f} EUR | verfuegbar {verf}')
        print(f'{"dP":>6} {"Preis":>7} {"Umsatz":>10} {"Delta":>9} '
              f'{"Delta%":>7} {"BE-Naechte":>10} {"BE-Ausl":>7} {"erf.Nachfr.":>11}')
        for z in zeilen:
            print(f'{z[1]:>+6.0f} {z[2]:>7.2f} {z[3]:>10.2f} {z[4]:>+9.2f} '
                  f'{z[5]:>+7.1f} {z[6]:>10.1f} {z[7]:>7.1f} {z[8]:>+11.1f}')

    # Monats-Szenarien (gleiche Rechnung, Basis = Monat) als eigene CSV.
    kopf_m, zeilen_m = monats_szenarien()
    ziel_m = os.path.join(OUT, 'preisszenarien_monat.csv')
    with open(ziel_m, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh, delimiter=';', lineterminator='\n')
        w.writerow(kopf_m)
        for z in zeilen_m:
            w.writerow(_csv_zeile(z, kopf_m))
    print(f'\nMonats-Szenarien: {ziel_m} ({len(zeilen_m)} Zeilen, '
          f'{len(kopf_m)} Spalten)')
    for m in sorted({z[0] for z in zeilen_m}):
        ref = [z for z in zeilen_m if z[0] == m and abs(z[4]) < 0.0001][0]
        print(f'  {ref[0]} ({ref[1]}): ADR {ref[5]:.2f} EUR | '
              f'Auslastung {ref[12]:.1f} % | Umsatz {ref[6]:.2f} EUR')

    print('\nHinweis: "Umsatz" haelt die Auslastung KONSTANT - reine Preiswirkung.')
    print('"erf.Nachfr." = noetige Nachfrageaenderung fuer den Break-even:')
    print('negativ = so viel darf ich verlieren, positiv = so viel brauche ich.')
    print('CSV-Format: Semikolon, Dezimalkomma, UTF-8 BOM (deutsche Schreibweise).')


if __name__ == '__main__':
    main()
