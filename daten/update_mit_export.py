#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neuen Airbnb-Export an den Roh-Bestand anhaengen und die Kette neu fahren.

Aufruf:
    python3 daten/update_mit_export.py /pfad/neuer_export.csv [weitere.csv ...] [--ende-auto]

  --ende-auto  hebt ENDE in build_kalender_tagesbasis.py auf die spaeteste Abreise an
               (verlaengert nur). Ohne den Schalter bricht das Skript ab und nennt die
               Zeile, die angepasst werden muss.

Ablauf:
  1. Neuen Export lesen und gegen den Roh-Bestand (raw/airbnb_master.csv)
     abgleichen: neue Zeilen anhaengen, Dubletten ueberspringen, denselben
     Vorgang mit korrigiertem Betrag als Korrektur uebernehmen.
  2. Roh-Bestand speichern - Spalte `Details` bleibt leer (Zahlungsadresse).
  3. Kette neu fahren: build_datasets -> build_kalender_tagesbasis ->
     add_flags_to_kalender -> build_xlsx.
  4. Kennzahlen vorher/nachher zeigen und warnen, wenn neue Naechte ausserhalb
     der Buchbarkeitsfenster liegen (PHASEN/ENDE).

Warum auf Roh-Ebene anhaengen und nicht in buchungen.csv:
  buchungen.csv ist abgeleitet. `Naechte_Belegt` ist die Vereinigung
  ueberlappender Aufenthalte: eine einzeln angehaengte Zeile kann sie nicht
  berechnen, und sie aendert sich rueckwirkend fuer vorhandene Zeilen, wenn der
  neue Aufenthalt sie ueberlappt. `Betriebsphase`, `ADR_Netto`, `Vorlauf_Tage`
  und die Storno-Erkennung haengen ebenfalls an der Gesamttabelle. Deshalb:
  Rohzeilen sammeln, danach alles neu berechnen lassen.
"""
import csv
import collections
import datetime
import os
import re
import shutil
import subprocess
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
BASIS = os.path.dirname(HIER)
MASTER = os.environ.get('AIRBNB_MASTER', os.path.join(BASIS, 'raw', 'airbnb_master.csv'))
KETTE = ['build_datasets.py', 'build_kalender_tagesbasis.py',
         'add_flags_to_kalender.py']
XLSX = os.path.join('reports', 'build_xlsx.py')
FELDER = ['Datum', 'Typ', 'Buchungsdatum', 'Startdatum', 'Enddatum', 'Nächte',
          'Details', 'Währung', 'Betrag', 'Ausgezahlt', 'Servicegebühr']


def lies(pfad):
    with open(pfad, encoding='utf-8-sig', newline='') as fh:
        r = csv.DictReader(fh)
        kopf = r.fieldnames
        zeilen = [{k: (v or '').strip() for k, v in z.items() if k} for z in r]
    return kopf, zeilen


def exakt(z):
    """Eindeutiger Zeilenschluessel. Betraege gehoeren dazu, weil derselbe
    Aufenthalt zweimal bezahlt werden kann (Verlaengerung, Mai 2026: 98,69 +
    170,44 bei identischem Zeitraum)."""
    typ = z.get('Typ', '')
    if typ == 'Buchung':
        felder = ['Typ', 'Buchungsdatum', 'Startdatum', 'Enddatum', 'Betrag']
    elif typ == 'Payout':
        felder = ['Typ', 'Datum', 'Ausgezahlt']
    else:
        felder = [f for f in FELDER if f != 'Details']
    return tuple(z.get(f, '') for f in felder)


def lose(z):
    """Schluessel ohne Betrag: erkennt denselben Vorgang mit korrigiertem Betrag."""
    typ = z.get('Typ', '')
    if typ == 'Buchung':
        return ('Buchung', z.get('Buchungsdatum', ''), z.get('Startdatum', ''),
                z.get('Enddatum', ''))
    if typ == 'Payout':
        return ('Payout', z.get('Datum', ''))
    return exakt(z)


def als_datum(s):
    try:
        m, d, y = s.split('/')
        return datetime.date(int(y), int(m), int(d))
    except (ValueError, AttributeError):
        return datetime.date(1900, 1, 1)


def zahl(s):
    s = (s or '').strip()
    if not s:
        return 0.0
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def kennzahlen():
    """Buchungen/Umsatz/Naechte aus buchungen.csv, Auslastung aus kalender.csv."""
    p = os.path.join(HIER, 'buchungen.csv')
    if not os.path.exists(p):
        return None
    b = lies(p)[1]
    umsatz = sum(zahl(z['Netto_Betrag']) for z in b)
    naechte = sum(int(zahl(z['Naechte_Belegt'])) for z in b)
    k = lies(os.path.join(HIER, 'kalender.csv'))[1]
    phasen = {}
    for z in k:
        ph = z.get('Betriebsphase', '')
        if not ph or z.get('Verfuegbar') != 'ja' and z.get('Belegt') != 'ja':
            continue
        v, bl = phasen.get(ph, (0, 0))
        phasen[ph] = (v + (z.get('Verfuegbar') == 'ja'), bl + (z.get('Belegt') == 'ja'))
    return {'buchungen': len(b), 'umsatz': umsatz, 'naechte': naechte,
            'adr': umsatz / naechte if naechte else 0, 'phasen': phasen}


def phasen_und_ende():
    """PHASEN-Fenster und ENDE aus build_kalender_tagesbasis.py lesen."""
    txt = open(os.path.join(HIER, 'build_kalender_tagesbasis.py'), encoding='utf-8').read()
    phasen = []
    block = re.search(r'PHASEN\s*=\s*\[(.*?)\]', txt, re.S)
    if block:
        for m in re.finditer(r'datetime\.date\((\d+),\s*(\d+),\s*(\d+)\),\s*'
                             r'datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)', block.group(1)):
            g = [int(x) for x in m.groups()]
            phasen.append((datetime.date(*g[:3]), datetime.date(*g[3:])))
    m = re.search(r'ENDE\s*=\s*datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)', txt)
    return phasen, (datetime.date(*[int(x) for x in m.groups()]) if m else None)


def ausschluss_ab():
    """AUSSCHLIESSEN_AB aus build_datasets.py lesen (2020er Zeilen fallen raus)."""
    txt = open(os.path.join(HIER, 'build_datasets.py'), encoding='utf-8').read()
    m = re.search(r'AUSSCHLIESSEN_AB\s*=\s*datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)', txt)
    return datetime.date(*[int(x) for x in m.groups()]) if m else datetime.date(2021, 1, 1)


def setze_ende(neu):
    """ENDE in build_kalender_tagesbasis.py verlaengern (nur nach hinten)."""
    p = os.path.join(HIER, 'build_kalender_tagesbasis.py')
    txt = open(p, encoding='utf-8').read()
    m = re.search(r'ENDE\s*=\s*datetime\.date\((\d+),\s*(\d+),\s*(\d+)\)', txt)
    txt = txt[:m.start()] + f'ENDE = datetime.date({neu.year}, {neu.month}, {neu.day})' + txt[m.end():]
    open(p, 'w', encoding='utf-8').write(txt)


def zeige(bez, k):
    if not k:
        return
    print(f'{bez}: {k["buchungen"]} Buchungen · {k["naechte"]} belegte Naechte · '
          f'{k["umsatz"]:.2f} EUR · ADR {k["adr"]:.2f} EUR')
    for ph, (v, b) in sorted(k['phasen'].items()):
        pct = f'{b / v * 100:.1f} %' if v else '—'
        warn = '   <-- ueber 100 %: belegte Naechte ausserhalb des Fensters?' if b > v else ''
        print(f'    {ph}: {b}/{v} = {pct}{warn}')


def main():
    args = sys.argv[1:]
    ende_auto = '--ende-auto' in args
    neue = [a for a in args if not a.startswith('--')]
    if not neue:
        raise SystemExit(__doc__.strip().splitlines()[3].strip())

    if os.path.exists(MASTER):
        kopf, bestand = lies(MASTER)
        print(f'Roh-Bestand: {MASTER} ({len(bestand)} Zeilen)')
    else:
        quelle = next((p for p in [os.environ.get('AIRBNB_RAW_CSV', ''),
                                   os.path.join(BASIS, 'raw', 'airbnb_.csv'),
                                   os.path.join(BASIS, 'data', 'raw', 'airbnb_.csv'),
                                   '/data/.openclaw/workspace/airbnb-data/raw/Einnahmen/airbnb_.csv']
                       if p and os.path.exists(p)), None)
        if not quelle:
            raise SystemExit('Kein Roh-Bestand und kein Ausgangsexport gefunden. '
                             'AIRBNB_RAW_CSV auf den vorhandenen Export setzen.')
        kopf, bestand = lies(quelle)
        print(f'Roh-Bestand angelegt aus: {quelle} ({len(bestand)} Zeilen)')

    fehlend = [f for f in FELDER if f not in kopf]
    if fehlend:
        raise SystemExit(f'Spalten fehlen im Export: {fehlend}')

    vorher = kennzahlen()
    exakt_idx = {exakt(z): z for z in bestand}
    lose_idx = collections.defaultdict(list)
    for z in bestand:
        lose_idx[lose(z)].append(z)

    neu, dubletten, korrekturen, mehrdeutig = [], 0, [], []
    for pfad in neue:
        k2, zeilen = lies(pfad)
        for z in zeilen:
            e = exakt(z)
            abw = lambda alt: [f'{f}: {alt.get(f)!r} -> {z.get(f)!r}'
                               for f in FELDER if f != 'Details'
                               and alt.get(f, '') != z.get(f, '')]
            if e in exakt_idx:
                dubletten += 1
                d = abw(exakt_idx[e])
                if d:
                    korrekturen.append((z.get('Startdatum'), z.get('Typ'), d))
                continue
            kandidaten = lose_idx.get(lose(z), [])
            if len(kandidaten) == 1:
                # derselbe Vorgang, anderer Betrag -> Korrektur uebernehmen
                alt = kandidaten[0]
                korrekturen.append((z.get('Startdatum'), z.get('Typ'), abw(alt)))
                bestand[bestand.index(alt)] = z
                exakt_idx.pop(exakt(alt), None)
                exakt_idx[e] = z
                lose_idx[lose(alt)] = [z]
                continue
            if len(kandidaten) > 1:
                mehrdeutig.append((z.get('Startdatum'), z.get('Typ'), z.get('Betrag')))
                continue
            neu.append(z)
            exakt_idx[e] = z
            lose_idx[lose(z)].append(z)

    print(f'\nNeue Zeilen: {len(neu)} | Dubletten uebersprungen: {dubletten} '
          f'| Korrekturen uebernommen: {len(korrekturen)} '
          f'| mehrdeutig (bitte pruefen): {len(mehrdeutig)}')
    for start, typ, d in korrekturen:
        print(f'  ~ Korrektur ({typ}, Start {start}): ' + '; '.join(d))
    for start, typ, betrag in mehrdeutig:
        print(f'  ? mehrdeutig ({typ}, Start {start}, Betrag {betrag}): '
              'mehrere gleichartige Zeilen vorhanden - nicht automatisch uebernommen.')
    if not neu and not korrekturen:
        print('  -> keine Aenderungen, Datenbestand unveraendert.')
        return

    for z in neu:
        z['Details'] = ''          # Zahlungsadresse: bleibt draussen
    alle = bestand + neu
    alle.sort(key=lambda z: (als_datum(z.get('Datum', '')), z.get('Typ', '')))
    os.makedirs(os.path.dirname(MASTER), exist_ok=True)
    with open(MASTER, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FELDER)
        w.writeheader()
        for z in alle:
            w.writerow({f: z.get(f, '') for f in FELDER})
    print(f'Roh-Bestand geschrieben: {MASTER} ({len(alle)} Zeilen)')

    # --- Vorab-Pruefung: passen die neuen Naechte in die Buchbarkeitsfenster? ---
    phasen, ende = phasen_und_ende()
    grenze = ausschluss_ab()
    buchungen = [z for z in alle if z.get('Typ') == 'Buchung' and z.get('Startdatum')
                 and als_datum(z['Startdatum']) >= grenze]
    spaeteste = max((als_datum(z['Enddatum']) for z in buchungen), default=None)
    ausserhalb = set()
    for z in buchungen:
        tag, ab = als_datum(z['Startdatum']), als_datum(z['Enddatum'])
        while tag < ab:
            if not any(a <= tag <= b for a, b in phasen):
                ausserhalb.add(tag)
            tag += datetime.timedelta(days=1)
    if ausserhalb:
        print(f'\n! {len(ausserhalb)} Nacht/Naechte liegen in keiner Buchbarkeitsphase '
              f'(z. B. {min(ausserhalb).strftime("%d.%m.%Y")}).')
        print('  -> PHASEN in build_kalender_tagesbasis.py ergaenzen. Belegte Naechte')
        print('     ausserhalb zaehlen in den Zaehler, aber nicht in den Nenner der')
        print('     Auslastung - sie kann dadurch ueber 100 % gehen.')
    if ende and spaeteste and spaeteste > ende:
        if ende_auto:
            setze_ende(spaeteste)
            print(f'ENDE angehoben: {ende.strftime("%d.%m.%Y")} -> '
                  f'{spaeteste.strftime("%d.%m.%Y")}')
        else:
            print(f'\n! Spaeteste Abreise {spaeteste.strftime("%d.%m.%Y")} liegt nach ENDE '
                  f'({ende.strftime("%d.%m.%Y")}) in build_kalender_tagesbasis.py.')
            print('  Ohne Anhebung bricht add_flags_to_kalender.py ab (Tage fehlen in der')
            print('  Tagesbasis). ENDE von Hand setzen oder mit --ende-auto laufen lassen')
            print('  (verlaengert nur, kuerzt nie).')
            raise SystemExit('Kette nicht gestartet - Datenbestand unveraendert.')

    print('\n--- Kette ---')
    env = dict(os.environ, AIRBNB_RAW_CSV=MASTER)
    for skript in KETTE:
        r = subprocess.run([sys.executable, os.path.join(HIER, skript)],
                           cwd=BASIS, env=env, capture_output=True, text=True)
        print(f'[{skript}] exit {r.returncode}')
        if r.returncode:
            print(r.stdout[-1500:]); print(r.stderr[-1500:])
            raise SystemExit(f'{skript} fehlgeschlagen - Datenbestand nicht konsistent.')
        for zeile in r.stdout.strip().splitlines()[-4:]:
            print('   ', zeile)
    r = subprocess.run([sys.executable, os.path.join(BASIS, XLSX)],
                       cwd=BASIS, capture_output=True, text=True)
    print(f'[{XLSX}] exit {r.returncode}')

    # Power-BI-Abfrage auf kalender_tagesaktuell.csv (falls noch im Modell)
    kopie = os.path.join(HIER, 'kalender_tagesaktuell.csv')
    if os.path.exists(kopie):
        shutil.copyfile(os.path.join(HIER, 'kalender.csv'), kopie)
        print('Hinweis: kalender_tagesaktuell.csv mitaktualisiert (Abfrage im '
              'Power-BI-Modell). Sauber waere, in Power Query auf kalender.csv umzustellen.')

    print('\n--- Kennzahlen ---')
    zeige('vorher ', vorher)
    zeige('nachher', kennzahlen())
    print('\nFertig. In Power BI noch "Aktualisieren" klicken.')


if __name__ == '__main__':
    main()
