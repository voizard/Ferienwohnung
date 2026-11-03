#!/usr/bin/env python3
"""Baut eine Power-BI-taugliche Excel-Arbeitsmappe ohne externe Bibliothek.

XLSX = ZIP mit XML. Wir schreiben die Teile selbst (inline strings,
Datums-Seriennummern, eigene Zellstile fuer Header/Datum/Waehrung).
"""
import csv, os, re, sys, zipfile, datetime as dt
from xml.sax.saxutils import escape

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(BASE, 'daten')
OUT = os.path.join(D, 'Airbnb_Datensatz_PowerBI.xlsx')
EPOCH = dt.date(1899, 12, 30)
ISO = re.compile(r'^\d{4}-\d{2}-\d{2}$')
MONEY = {'Netto_Betrag', 'Servicegebuehr', 'Brutto_Betrag', 'ADR_Netto', 'Betrag',
         'Preis_je_Nacht_EUR', 'Umsatz_Konstant_EUR', 'Umsatz_Delta_EUR'}
SEP = ';'          # deutscher CSV-Trenner in daten/*.csv

S_HEAD, S_TXT, S_DATE, S_MONEY, S_INT = 1, 0, 2, 3, 0


def colref(i):
    s = ''
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def read_csv(name):
    with open(os.path.join(D, name), encoding='utf-8-sig', newline='') as fh:
        return list(csv.reader(fh, delimiter=SEP))


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
                    # Deutsche Schreibweise: Dezimalkomma (z. B. 40,46).
                    f = float(v.replace('.', '').replace(',', '.')) if ',' in v else float(v)
                    row.append(int(f) if f == int(f) else f)
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
    ['Blatt buchungen', '53 Buchungen (Faktentabelle). Eine Zeile = eine Buchung.'],
    ['Blatt anpassungen', 'Airbnb-Anpassungen/Mediationen (Faktentabelle). Zeilen vor 2021 sind ausgeschlossen, damit keine verwaiste Anpassung ohne Gegenstueck in buchungen entsteht.'],
    ['Blatt kalender', 'Datumstabelle, taeglich 2025-10-24 bis 2026-11-01. In Power BI als Datumstabelle markieren (Spalte Datum).'],
    ['Spalte Teilmonat', 'ja = Monat wird vom Buchbarkeitsfenster angeschnitten (Okt 2025, Dez 2025, Mai 2026). Diese Monate im Monatsvergleich ausblenden oder kennzeichnen - ihre Auslastungsquote ist nicht mit vollen Monaten vergleichbar (weniger verfuegbare Naechte). Alle anderen Monate: nein.'],
    ['Blatt betriebsphasen', 'Buchbarkeitsfenster je Vermietungsphase - steuert die Auslastung.'],
    ['WICHTIG: Umsatz != Belegung', 'Netto_Betrag ist der Umsatz. Naechte_Belegt ist die Belegung. Beide koennen auseinanderfallen: (1) eine stornierte, aber trotzdem ausgezahlte Buchung hat Umsatz und 0 belegte Naechte; (2) eine Verlaengerung desselben Gastes zahlt zweimal, belegt aber nur einmal.'],
    ['Naechte_Belegt', 'Ist eine VEREINIGUNG der Aufenthaltszeitraeume, keine Summe. Ueberlappende Aufenthalte zaehlen nur einmal - sonst sinkt der ADR kuenstlich um ~6 %.'],
    ['Gebuehrenmodell', 'Phase 1: Split Fee, Host zahlt 3 % + MwSt = 3,57 %, Gast zahlt zusaetzlich 14,1-16,5 % (im Checkout sichtbar). Phase 2: Host-Only Fee, Host zahlt 15,5 % + MwSt = 18,45 %, Gast sieht nur den Endpreis.'],
    ['Spalte Brutto_Betrag', 'Achtung: bedeutet in beiden Phasen etwas anderes. In Phase 1 der Listenpreis OHNE Guestgegebuehr, in Phase 2 der Endpreis des Gastes. Nicht naiv ueber die Phasen vergleichen.'],
    ['Auslastung / verfuegbare Naechte', 'Nur Naechte im Buchbarkeitsfenster zaehlen, gesperrte Naechte sind abzuziehen. Phase 2 hat 163 Kalendertage (22.05.-31.10.2026) minus 10 gesperrte (07.-16.08.2026) = 153 verfuegbare Naechte.'],
    ['Beziehungen', 'kalender[Datum] (1) -> buchungen[Anreise] (*). betriebsphasen[Betriebsphase] (1) -> buchungen[Betriebsphase] (*).'],
    ['Datums-Spalten', 'Buchungsdatum, Anreise, Abreise (buchungen); Datum (kalender); Verfuegbar_ab, Verfuegbar_bis, Gesperrt_ab, Gesperrt_bis (betriebsphasen).'],
    ['Nicht enthalten', 'Keine personenbezogenen Gaestedaten. Die Details-Spalte des Airbnb-Exports (Zahlungsadresse) wurde bewusst verworfen.'],
    ['Ausgeschlossen', 'Alle Buchungen vor 2021 (24 Zeilen aus Jun-Aug 2020) - sie gehoeren nicht zu den beiden Vermietungsphasen. Ab 2026-11-02 enthaelt der Bestand auch die Buchungen bis 31.10.2026 (Phase 2 laeuft ohne Saisonbruch weiter).'],
    ['Kosten', 'Noch nicht enthalten: Nebenkosten, Reinigung, Instandhaltung. Ein Deckungsbeitrag ist daher derzeit nicht berechenbar.'],
    ['Blatt preisszenarien', 'Preis-Szenarien fuer die Seite "Preis testen" (Preis -30 % bis +30 %). Umsatz bei KONSTANTER Auslastung und Break-even. Basis: gesamt + beide Phasen. Erzeugt von analyse/preisszenario.py.'],
    ['Blatt preisszenarien_monat', 'Gleiche Rechnung je Monat (Basis = YYYY-MM), 13 Preisschritte je Monat = 117 Zeilen. ZUORDNUNG AUF TAGESBASIS: eine Nacht zaehlt in den Monat, in dem sie LIEGT - eine Buchung 28.09.-03.10. also teils September, teils Oktober. Naechte + verfuegbare Naechte kommen aus kalender.csv, der Umsatz wird nach Kalendernaechten verteilt. Damit ist die Monatssumme konsistent zur Gesamtauslastung (176/204 = 86,27 %) und deckt sich mit BEFUNDE.md. SLICER: Power BI erkennt Basis ("2025-10") beim Import als DATUM und zeigt im Slicer nur den Monatsersten. Deshalb fuer den Slicer die Spalte Monat ("Oktober 2025", reiner Text) verwenden und nach Monat_Sort (202510) sortieren. Monat_Datum ist bewusst der LETZTE Tag des Monats - so beschriftet Power BI eine Datumsachse mit "Oktober 2025" statt "1. Oktober". ACHTUNG Teilmonate (2025-10, 2025-12, 2026-05): dort schneidet das Buchbarkeitsfenster den Monat an, die Auslastung ist nicht mit vollen Monaten vergleichbar (Spalte Teilmonat = ja). Gleiche Ehrlichkeitsgrenze wie oben: keine gemessene Preiselastizitaet.'],
    ['WICHTIG: keine Preiselastizitaet', 'Der Datensatz enthaelt KEINE gemessene Preiselastizitaet. Modell B erklaert den erzielten Preis, nicht die Nachfragereaktion. "Umsatz bei konstanter Auslastung" ist die Obergrenze; die Break-even-Spalte ist die Entscheidungsgroesse. Eine Elastizitaet ist eine Annahme.'],
    ['Spalten Ampel/Hinweis/Ist_Auslastung_Pct', 'Fertige Hilfsspalten fuer die Seite "Preis testen" OHNE DAX: Ampel = gruen/rot/unmoeglich/referenz (fuer die bedingte Hintergrundfarbe), Hinweis = Klartext ("darf 9,1 % verlieren"), Ist_Auslastung_Pct = Vergleichswert. unmoeglich = Break-even-Auslastung ueber 100 % - die noetigen Naechte gibt es gar nicht, die Preissenkung ist nicht kompensierbar. Die Spalten *_Pct stehen als Prozentpunkt-Zahl (86,27 = 86,27 %) - KEIN Prozentformat darauf legen.'],
    ['Spalte Zeilenfarbe', 'Enthaelt NUR in der Referenzzeile (Preis_Delta_Pct = 0) einen Hex-Wert (#E8EEF4), sonst leer. Damit laesst sich die Referenzzeile in Power BI mit EINEM Dialog je Spalte hervorheben: Spalte -> Formatieren -> Zellenlemente -> Hintergrundfarbe -> Bedingte Formatierung -> Formatstil "Feldwert" -> Feld Zeilenfarbe. Fuer die ganze Zeile auf jeder sichtbaren Spalte wiederholen (Preis_Delta_Pct, Preis_je_Nacht_EUR, Umsatz_Konstant_EUR, Break_even_Auslastung_Pct, Hinweis). Fett geht in Power BI nur spaltig, nie zeilenweise - die Hervorhebung traegt daher Fuelle + Rahmen.'],
    ['Format (Festlegung Chris)', 'Alle Exporte in deutscher Schreibweise: Semikolon als Trenner, Dezimalkomma, UTF-8 mit BOM. Sonst liest ein deutsches Power BI den Punkt als Tausenderpunkt (aus 40,46 wird 4046).'],
]
sheets.append(('LIESMICH', lh, liesmich))

for name, fname in [('buchungen', 'buchungen.csv'), ('anpassungen', 'anpassungen.csv'), ('kalender', 'kalender.csv')]:
    header, rows = coerce(read_csv(fname))
    sheets.append((name, header, rows))

ph_header = ['Betriebsphase', 'Verfuegbar_ab', 'Verfuegbar_bis', 'Kalendertage',
             'Gesperrt_ab', 'Gesperrt_bis', 'Gesperrte_Naechte', 'Verfuegbare_Naechte']
ph_rows = [
    ['Phase 1 (Okt-Dez 2025)', dt.date(2025, 10, 24), dt.date(2025, 12, 13), 51, None, None, 0, 51],
    ['Phase 2 (Mai-Okt 2026)', dt.date(2026, 5, 22), dt.date(2026, 10, 31), 163,
     dt.date(2026, 8, 7), dt.date(2026, 8, 16), 10, 153],
]
sheets.append(('betriebsphasen', ph_header, ph_rows))

# Preis-Szenarien als typisiertes Blatt (typisierte Zellen -> kein
# Locale-Problem beim Import). Erzeugt von analyse/preisszenario.py.
sys.path.insert(0, os.path.join(BASE, 'analyse'))
from preisszenario import alle_szenarien, monats_szenarien  # noqa: E402
sp_header, sp_rows = alle_szenarien()
sheets.append(('preisszenarien', sp_header, sp_rows))

# Gleiche Rechnung je Monat (Basis = 'YYYY-MM'), eine Zeile je Monat und
# Preisschritt. Verfuegbare Naechte je Monat aus kalender.csv.
mp_header, mp_rows = monats_szenarien()
sheets.append(('preisszenarien_monat', mp_header, mp_rows))

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
