#!/usr/bin/env python3
"""Baut aus dem Airbnb-Roh-Export (`airbnb_.csv`) import-fertige CSV-Dateien
für das Power-BI-Portfolioprojekt.

Erzeugt in ../airbnb-portfolio/daten/:
  - buchungen.csv       (eine Zeile pro Buchung)
  - anpassungen.csv     (Airbnb-Anpassungen/Mediationen)
  - kalender.csv        (Datumstabelle)

Modellierungsentscheidungen (mit dem Host geklärt):
  1. Datensätze aus 2020 werden ausgeschlossen.
  2. Details-Spalte wird verworfen: enthält die Zahlungsadresse (PII).
  3. Payout-Zeilen werden verworfen: sie spiegeln jede Buchung und würden
     bei einer Summierung doppelt zählen.
  4. Umsatz != Belegung. Klärung durch den Host:
       - Sept 2026: Same-Day-Storno, Auszahlung erfolgte trotzdem
         -> Umsatz ja, Belegung nein.
       - Mai 2026: Verlängerung desselben Gastes, beide Zahlungen real
         -> Umsatz ja (2 Zahlungen), Belegung nur einmal (5 Nächte).
     Daher getrennte Spalten `Netto_Betrag` (Umsatz) und `Naechte_Belegt`.
  5. Überlappende Aufenthalte zählen für die Belegung nur EINMAL:
     `Naechte_Belegt` = Nächte, die noch nicht von einem anderen Aufenthalt
     abgedeckt sind (Vereinigung der Zeiträume).
  6. Ausgabe: UTF-8 mit BOM, Komma als Trenner, Punkt als Dezimaltrenner,
     ISO-Datumsformat (yyyy-mm-dd) -> eindeutig für Power Query.
"""
import csv
import datetime
import os

# Roh-Export (nicht im Repo: enthaelt personenbezogene Zahlungsdaten).
# Pfad per Umgebungsvariable AIRBNB_RAW_CSV setzen oder hier ablegen.
_KANDIDATEN = [os.environ.get('AIRBNB_RAW_CSV', ''),
               'raw/airbnb_.csv', 'data/raw/airbnb_.csv',
               '../airbnb-data/raw/Einnahmen/airbnb_.csv']
SRC = next((p for p in _KANDIDATEN if p and os.path.exists(p)), 'raw/airbnb_.csv')
OUT = os.path.dirname(os.path.abspath(__file__))

AUSSCHLIESSEN_AB = datetime.date(2021, 1, 1)   # alles davor (2020) raus
# Bestätigte Stornos: Auszahlung erfolgt, Aufenthalt fand nicht statt.
# Schlüssel: (Buchungsdatum, Anreise, Netto-Betrag)
STORNO = {
    (datetime.date(2026, 8, 11), datetime.date(2026, 9, 24), 127.43),
}
# Buchbarkeitsfenster je Phase = Nenner der Auslastung (Annahme, vom Host
# bestätigt: Phase 2 erst ab 22.05.2026 buchbar).
FENSTER = {
    'Phase 1 (Okt-Dez 2025)': (datetime.date(2025, 10, 24), datetime.date(2025, 12, 13)),
    'Phase 2 (Mai-Sep 2026)': (datetime.date(2026, 5, 22), datetime.date(2026, 9, 30)),
}

# Gesperrte Zeiträume (Eigennutzung/Reparatur) – zählen NICHT als verfügbar.
# Vom Host bestätigt: 07.08.2026 bis 16.08.2026 = 10 Nächte geblockt.
# (Vorgänger B013 reist am 07.08. ab, Nachfolger B012 kommt am 17.08. – keine Kollision.)
BLOCKIERT = {
    'Phase 2 (Mai-Sep 2026)': [(datetime.date(2026, 8, 7), datetime.date(2026, 8, 16))],
}


def num(s):
    """Zahl aus Airbnb-Export: gemischte Dezimaltrenner (300.93 vs 68,07)."""
    s = (s or '').strip()
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def dt(s):
    s = (s or '').strip()
    if not s:
        return None
    m, d, y = s.split('/')
    return datetime.date(int(y), int(m), int(d))


def phase(d):
    if d is None:
        return None
    if d < datetime.date(2026, 1, 1):
        return 'Phase 1 (Okt-Dez 2025)'
    return 'Phase 2 (Mai-Sep 2026)'


def load(path):
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


rows = load(SRC)
buch = [r for r in rows if r['Typ'] == 'Buchung']
adjs = [r for r in rows if r['Typ'] not in ('Buchung', 'Payout')]

vorher = len(buch)
buch = [r for r in buch if dt(r['Startdatum']) and dt(r['Startdatum']) >= AUSSCHLIESSEN_AB]
print(f'2020 ausgeschlossen: {vorher - len(buch)} Buchungen entfernt')

# --- Vereinigung der Aufenthaltszeiträume -------------------------------
sortiert = sorted(buch, key=lambda r: (dt(r['Startdatum']), dt(r['Buchungsdatum'])))
belegt = {}
naechte_belegt = {}
doppel = set()
for r in sortiert:
    an, ab = dt(r['Startdatum']), dt(r['Enddatum'])
    s = (dt(r['Buchungsdatum']), an, num(r['Betrag']))
    if s in STORNO:
        # Storno: Auszahlung ja, aber die Nächte waren nicht belegt.
        # Darf deshalb keine Nächte fuer die Vereinigung beanspruchen.
        naechte_belegt[s] = 0
        continue
    neu, d = 0, an
    while d < ab:
        if d in belegt:
            doppel.add(s)
        else:
            belegt[d] = s
            neu += 1
        d += datetime.timedelta(days=1)
    naechte_belegt[s] = neu

# --- buchungen.csv ------------------------------------------------------
head = ['Buchung_ID', 'Betriebsphase', 'Waehrung', 'Buchungsdatum', 'Anreise',
        'Abreise', 'Naechte', 'Netto_Betrag', 'Servicegebuehr', 'Brutto_Betrag',
        'ADR_Netto', 'Naechte_Belegt', 'Storno', 'Ueberlappung', 'Belegung_Hinweis',
        'Vorlauf_Tage', 'Anreisetag_Wochentag', 'Jahr', 'Monat']

out = []
for i, r in enumerate(buch, 1):
    an, ab = dt(r['Startdatum']), dt(r['Enddatum'])
    bd = dt(r['Buchungsdatum'])
    netto = num(r['Betrag'])
    fee = num(r['Servicegebühr']) or 0.0
    naechte = int(r['Nächte']) if r['Nächte'] else None
    s = (bd, an, netto)
    ist_storno = s in STORNO
    nb = 0 if ist_storno else naechte_belegt[s]
    if ist_storno:
        hinweis = 'Storno – Auszahlung erfolgte trotzdem'
    elif s in doppel:
        hinweis = 'Überlappender Zeitraum – Nächte nur einmal gezählt'
    else:
        hinweis = ''
    out.append({
        'Buchung_ID': f'B{i:03d}',
        'Betriebsphase': phase(an),
        'Waehrung': r['Währung'],
        'Buchungsdatum': bd.isoformat() if bd else '',
        'Anreise': an.isoformat() if an else '',
        'Abreise': ab.isoformat() if ab else '',
        'Naechte': naechte or '',
        'Netto_Betrag': f'{netto:.2f}' if netto is not None else '',
        'Servicegebuehr': f'{fee:.2f}',
        'Brutto_Betrag': f'{(netto or 0) + fee:.2f}',
        'ADR_Netto': f'{netto / naechte:.2f}' if netto and naechte else '',
        'Naechte_Belegt': nb,
        'Storno': 'ja' if ist_storno else '',
        'Ueberlappung': 'ja' if s in doppel else '',
        'Belegung_Hinweis': hinweis,
        'Vorlauf_Tage': (an - bd).days if (an and bd) else '',
        'Anreisetag_Wochentag': an.strftime('%A') if an else '',
        'Jahr': an.year if an else '',
        'Monat': an.month if an else '',
    })

os.makedirs(OUT, exist_ok=True)
with open(f'{OUT}/buchungen.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=head)
    w.writeheader()
    w.writerows(out)
print(f'buchungen.csv: {len(out)} Zeilen')

# Konsistenz zu Entscheidung 1: auch Anpassungen vor 2021 entfernen.
# Die -26.90 vom 26.06.2020 gehörte zu einer ausgeschlossenen 2020-Buchung und
# wäre sonst eine verwaiste Zeile ohne Gegenstück in `buchungen`.
_n0 = len(adjs)
adjs = [r for r in adjs if dt(r['Datum']) and dt(r['Datum']) >= datetime.date(2021, 1, 1)]
with open(f'{OUT}/anpassungen.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Datum', 'Typ', 'Buchungsdatum', 'Anreise', 'Abreise', 'Naechte', 'Betrag'])
    for r in adjs:
        w.writerow([dt(r['Datum']).isoformat() if dt(r['Datum']) else '', r['Typ'],
                    dt(r['Buchungsdatum']).isoformat() if dt(r['Buchungsdatum']) else '',
                    dt(r['Startdatum']).isoformat() if dt(r['Startdatum']) else '',
                    dt(r['Enddatum']).isoformat() if dt(r['Enddatum']) else '',
                    r['Nächte'], f"{num(r['Betrag']):.2f}"])
print(f'anpassungen.csv: {len(adjs)} Zeilen ({_n0 - len(adjs)} vor 2021 entfernt)')

start = min(dt(r['Startdatum']) for r in buch if dt(r['Startdatum']))
end = max(dt(r['Enddatum']) for r in buch if dt(r['Enddatum']))
with open(f'{OUT}/kalender.csv', 'w', encoding='utf-8-sig', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Datum', 'Jahr', 'Quartal', 'Monat', 'Monatsname', 'Kalenderwoche', 'Wochentag'])
    d, n = start, 0
    while d <= end:
        n += 1
        w.writerow([d.isoformat(), d.year, (d.month - 1) // 3 + 1, d.month,
                    d.strftime('%B'), d.isocalendar()[1], d.strftime('%A')])
        d += datetime.timedelta(days=1)
print(f'kalender.csv: {n} Zeilen ({start} bis {end})')

# --- Kennzahlen ---------------------------------------------------------
import collections
print('\n=== Kennzahlen je Betriebsphase ===')
agg = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0])
for r in out:
    k = r['Betriebsphase']
    agg[k][0] += 1
    agg[k][1] += float(r['Netto_Betrag'] or 0)
    agg[k][2] += int(r['Naechte'] or 0)
    agg[k][3] += int(r['Naechte_Belegt'])
    agg[k][4] += 1 if r['Storno'] else 0
for k in sorted(agg):
    n, ums, nae, nb, st = agg[k]
    print(f'  {k}: {n} Buchungen ({st} Storno) | Umsatz {ums:9.2f} EUR | '
          f'gebuchte Nächte {nae:3d} | belegte Nächte {nb:3d} | '
          f'ADR netto {ums / nb if nb else 0:6.2f} EUR')

print('\n=== Auslastung (Nächte im Buchbarkeitsfenster, ohne gesperrte Nächte) ===')
for k, (a, b) in FENSTER.items():
    verf = (b - a).days + 1
    sperren = BLOCKIERT.get(k, [])
    gesperrt = sum((min(be, b) - max(bs, a)).days + 1 for bs, be in sperren if bs <= b and be >= a)
    verf -= gesperrt
    belegt_im_fenster = sum(1 for d in belegt
                            if a <= d <= b and not any(bs <= d <= be for bs, be in sperren))
    ums = agg[k][1]
    print(f'  {k}: {a}–{b} = {(b - a).days + 1} Nächte, {gesperrt} gesperrt '
          f'→ {verf} verfügbar | belegt {belegt_im_fenster} '
          f'| Auslastung {belegt_im_fenster / verf * 100:5.1f}% | RevPAR {ums / verf:6.2f} EUR')
