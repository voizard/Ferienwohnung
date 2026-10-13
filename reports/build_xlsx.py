#!/usr/bin/env python3
"""Baut eine Power-BI-taugliche Excel-Arbeitsmappe ohne externe Bibliothek.

XLSX = ZIP mit XML. Wir schreiben die Teile selbst (inline strings,
Datums-Seriennummern, eigene Zellstile fuer Header/Datum/Waehrung).
"""
import csv, os, re, zipfile, datetime as dt
from xml.sax.saxutils import escape

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, 'daten')
OUT = os.path.join(D, 'Airbnb_Datensatz_PowerBI.xlsx')
EPOCH = dt.date(1899, 12, 30)
ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MONEY = {'Netto_Betrag', 'Servicegebuehr', 'Brutto_Betrag', 'ADR_Netto', 'Betrag'}

S_HEAD, S_TXT, S_DATE, S_MONEY, S_INT = 1, 0, 2, 3, 0


def colref(i):
    s = ''
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def read_csv(name):
    with open(os.path.join(D, name), encoding='utf-8-sig', newline='') as fh:
        return list(csv.reader(fh))


def cell_xml(ref, val, style):
    if val is None or val == '':
        return ''
    if isinstance(val, dt.date):
        return f'<c r="{ref}" s="{S_DATE}"><v>{(val - EPOCH).days}</v></c>'
    if isinstance(val, (int, float)):
        return f'<c r="{ref}" s="{style}"><v>{val}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(val))}</t></is></c>'


def build_sheet(header, rows, ncols=None):
    """Gibt (xml, ref_autofilter) zurueck. rows = Liste von Listen, Werte roh."""
    nc = ncols or len(header)
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    last = f'{colref(nc)}{len(rows) + 1}'
    out.append(f'<dimension ref="A1:{last}"/>')
    out.append(f'<sheetData>')
    hcells = ''.join(f'<c r="{colref(i+1)}1" s="{S_HEAD}" t="inlineStr"><is><t>{escape(str(h))}</t></is></c>'
                     for i, h in enumerate(header))
    out.append(f'<row r="1">{hcells}</row>')
    for ri, row in enumerate(rows, start=2):
        cells = []
        for ci, val in enumerate(row, start=1):
            name = header[ci - 1] if ci - 1 < len(header) else ''
            style = S_MONEY if name in MONEY else S_INT
            cells.append(cell_xml(f'{colref(ci)}{ri}', val, style))
        out.append(f'<row r="{ri}">{"".join(cells)}</row>')
    out.append('</sheetData>')
    out.append(f'<autoFilter ref="A1:{last}"/>')
    out.append('</worksheet>')
    return '\n'.join(out)


def coerce(table):
    """CSV-Tabelle (Liste von Listen) -> Header + typisierte Zeilen."""
    header = table[0]
    rows = []
    for raw in table[1:]:
        row = []
        for i, v in enumerate(raw):
            if v == '':
                row.append(None)
            elif ISO.match(v):
                row.append(dt.date.fromisoformat(v))
            else:
                try:
                    f = float(v)
                    row.append(int(f) if f == int(f) and '.' not in v else f)
                except ValueError:
                    row.append(v)
        rows.append(row)
    return header, rows


# --- Daten laden -------------------------------------------------------
sheets = []

lh = ['Thema', 'Inhalt']
liesmich = [
    ['Datei', 'Datenbasis fuer das Power-BI-Projekt "Ferienwohnung"'],
    ['Erstellt', '2026-09-29'],
    ['Blatt buchungen', '44 Buchungen (Faktentabelle). Eine Zeile = eine Buchung.'],
    ['Blatt anpassungen', 'Airbnb-Anpassungen/Mediationen (Faktentabelle). Zeilen vor 2021 sind ausgeschlossen, damit keine verwaiste Anpassung ohne Gegenstueck in buchungen entsteht.'],
    ['Blatt kalender', 'Datumstabelle, taeglich 2025-10-24 bis 2026-10-03. In Power BI als Datumstabelle markieren (Spalte Datum).'],
    ['Blatt betriebsphasen', 'Buchbarkeitsfenster je Vermietungsphase - steuert die Auslastung.'],
    ['WICHTIG: Umsatz != Belegung', 'Netto_Betrag ist der Umsatz. Naechte_Belegt ist die Belegung. Beide koennen auseinanderfallen: (1) eine stornierte, aber trotzdem ausgezahlte Buchung hat Umsatz und 0 belegte Naechte; (2) eine Verlaengerung desselben Gastes zahlt zweimal, belegt aber nur einmal.'],
    ['Naechte_Belegt', 'Ist eine VEREINIGUNG der Aufenthaltszeitraeume, keine Summe. Ueberlappende Aufenthalte zaehlen nur einmal - sonst sinkt der ADR kuenstlich um ~6 %.'],
    ['Gebuehrenmodell', 'Phase 1: Split Fee, Host zahlt 3 % + MwSt = 3,57 %, Gast zahlt zusaetzlich 14,1-16,5 % (im Checkout sichtbar). Phase 2: Host-Only Fee, Host zahlt 15,5 % + MwSt = 18,45 %, Gast sieht nur den Endpreis.'],
    ['Spalte Brutto_Betrag', 'Achtung: bedeutet in beiden Phasen etwas anderes. In Phase 1 der Listenpreis OHNE Guestgegebuehr, in Phase 2 der Endpreis des Gastes. Nicht naiv ueber die Phasen vergleichen.'],
    ['Auslastung / verfuegbare Naechte', 'Nur Naechte im Buchbarkeitsfenster zaehlen, gesperrte Naechte sind abzuziehen. Phase 2 hat 132 Kalendertage minus 10 gesperrte (07.-16.08.2026) = 122 verfuegbare Naechte.'],
    ['Beziehungen', 'kalender[Datum] (1) -> buchungen[Anreise] (*). betriebsphasen[Betriebsphase] (1) -> buchungen[Betriebsphase] (*).'],
    ['Datums-Spalten', 'Buchungsdatum, Anreise, Abreise (buchungen); Datum (kalender); Verfuegbar_ab, Verfuegbar_bis, Gesperrt_ab, Gesperrt_bis (betriebsphasen).'],
    ['Nicht enthalten', 'Keine personenbezogenen Gaestedaten. Die Details-Spalte des Airbnb-Exports (Zahlungsadresse) wurde bewusst verworfen.'],
    ['Ausgeschlossen', 'Alle Buchungen vor 2021 (24 Zeilen aus Jun-Aug 2020) - sie gehoeren nicht zu den beiden Vermietungsphasen.'],
    ['Kosten', 'Noch nicht enthalten: Nebenkosten, Reinigung, Instandhaltung. Ein Deckungsbeitrag ist daher derzeit nicht berechenbar.'],
]
sheets.append(('LIESMICH', lh, liesmich))

for name, fname in [('buchungen', 'buchungen.csv'), ('anpassungen', 'anpassungen.csv'), ('kalender', 'kalender.csv')]:
    header, rows = coerce(read_csv(fname))
    sheets.append((name, header, rows))

ph_header = ['Betriebsphase', 'Verfuegbar_ab', 'Verfuegbar_bis', 'Kalendertage',
             'Gesperrt_ab', 'Gesperrt_bis', 'Gesperrte_Naechte', 'Verfuegbare_Naechte']
ph_rows = [
    ['Phase 1 (Okt-Dez 2025)', dt.date(2025, 10, 24), dt.date(2025, 12, 13), 51, None, None, 0, 51],
    ['Phase 2 (Mai-Sep 2026)', dt.date(2026, 5, 22), dt.date(2026, 9, 30), 132,
     dt.date(2026, 8, 7), dt.date(2026, 8, 16), 10, 122],
]
sheets.append(('betriebsphasen', ph_header, ph_rows))

# --- XLSX schreiben ----------------------------------------------------
CT = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
      '<Default Extension="xml" ContentType="application/xml"/>',
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
      '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
for i in range(1, len(sheets) + 1):
    CT.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
CT.append('</Types>')

RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>')

wb = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>']
for i, (name, _, _) in enumerate(sheets, start=1):
    wb.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
wb.append('</sheets></workbook>')

wbrels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
          '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
for i in range(1, len(sheets) + 1):
    wbrels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
wbrels.append(f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>')
wbrels.append('</Relationships>')

STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd"/>
<numFmt numFmtId="165" formatCode="#,##0.00"/>
</numFmts>
<fonts count="2">
<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF0B4A8A"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="4">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('[Content_Types].xml', '\n'.join(CT))
    z.writestr('_rels/.rels', RELS)
    z.writestr('xl/workbook.xml', '\n'.join(wb))
    z.writestr('xl/_rels/workbook.xml.rels', '\n'.join(wbrels))
    z.writestr('xl/styles.xml', STYLES)
    for i, (name, header, rows) in enumerate(sheets, start=1):
        z.writestr(f'xl/worksheets/sheet{i}.xml', build_sheet(header, rows))

print('geschrieben:', OUT, os.path.getsize(OUT), 'Bytes')
for name, header, rows in sheets:
    print(f'  Blatt {name:16} {len(rows):4d} Zeilen x {len(header)} Spalten')
