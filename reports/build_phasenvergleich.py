#!/usr/bin/env python3
"""Baut den Phasen-Vergleich als Markdown + PDF (WeasyPrint)."""
import csv, os, datetime as dt
import markdown
from weasyprint import HTML

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'reports')
os.makedirs(OUT, exist_ok=True)

FENSTER = {
    'P1': (dt.date(2025, 10, 24), dt.date(2025, 12, 13)),
    'P2': (dt.date(2026, 5, 22), dt.date(2026, 9, 30)),
}
BLOCKIERT = {'P2': [(dt.date(2026, 8, 7), dt.date(2026, 8, 16))]}
PNAME = {'Phase 1 (Okt-Dez 2025)': 'P1', 'Phase 2 (Mai-Sep 2026)': 'P2'}


def d(s):
    return dt.date.fromisoformat(s) if s else None


def eur(x):
    return f"{x:,.2f}".replace(',', '#').replace('.', ',').replace('#', '.')


def pct(x, dec=1):
    return f"{x:.{dec}f}".replace('.', ',')


def sgn(x, dec=1):
    return ('+' if x >= 0 else '\u2212') + pct(abs(x), dec)


rows = list(csv.DictReader(open(os.path.join(BASE, 'daten', 'buchungen.csv'), encoding='utf-8-sig')))

agg = {k: dict(n=0, netto=0.0, brutto=0.0, fee=0.0, gebucht=0, belegt=0, storno=0.0) for k in FENSTER}
for r in rows:
    a = agg[PNAME[r['Betriebsphase']]]
    a['n'] += 1
    a['netto'] += float(r['Netto_Betrag']); a['brutto'] += float(r['Brutto_Betrag'])
    a['fee'] += float(r['Servicegebuehr'])
    a['gebucht'] += int(r['Naechte']); a['belegt'] += int(r['Naechte_Belegt'])
    if r['Storno'] == 'ja':
        a['storno'] += float(r['Netto_Betrag'])

belegt = []
for r in rows:
    if int(r['Naechte_Belegt']) == 0:
        continue
    x, ab = d(r['Anreise']), d(r['Abreise'])
    while x < ab:
        belegt.append(x); x += dt.timedelta(days=1)

for k, (wa, wb) in FENSTER.items():
    a = agg[k]
    sperren = BLOCKIERT.get(k, [])
    a['gesperrt'] = sum((min(be, wb) - max(bs, wa)).days + 1 for bs, be in sperren if bs <= wb and be >= wa)
    a['verf'] = (wb - wa).days + 1 - a['gesperrt']
    a['belegt_fenster'] = sum(1 for x in belegt if wa <= x <= wb and not any(bs <= x <= be for bs, be in sperren))
    a['ausl'] = a['belegt_fenster'] / a['verf'] * 100
    a['adr'] = a['netto'] / a['belegt']
    a['revpar'] = a['netto'] / a['verf']
    a['feep'] = a['fee'] / a['brutto'] * 100
    a['listen'] = a['brutto'] / a['belegt']
    a['aufenthalt'] = a['belegt'] / a['n']

p1, p2 = agg['P1'], agg['P2']

GF, GF_LO, GF_HI = 0.15, 0.141, 0.165
g1, g1lo, g1hi = p1['listen'] * (1 + GF), p1['listen'] * (1 + GF_LO), p1['listen'] * (1 + GF_HI)
g2 = p2['listen']
air1, air2 = g1 - p1['adr'], g2 - p2['adr']
d_gast = (g2 / g1 - 1) * 100
d_gast_lo = (g2 / g1hi - 1) * 100
d_gast_hi = (g2 / g1lo - 1) * 100
d_host = (p2['adr'] / p1['adr'] - 1) * 100
d_air = (air2 / air1 - 1) * 100
d_air_lo = (air2 / (g1lo - p1['adr']) - 1) * 100
d_air_hi = (air2 / (g1hi - p1['adr']) - 1) * 100
noetig = ((1 - p1['feep'] / 100) / (1 - p2['feep'] / 100) - 1) * 100
tats = (p2['listen'] / p1['listen'] - 1) * 100
mult_neu = 1 / (1 - p2['feep'] / 100)
mult_alt = 1 / (1 - p1['feep'] / 100)
share1 = air1 / g1 * 100
share2 = air2 / g2 * 100
share1_lo = (g1lo - p1['adr']) / g1lo * 100
share1_hi = (g1hi - p1['adr']) / g1hi * 100

md = f"""# Ferienwohnung \u2013 Vergleich der Vermietungsphasen

> Erstellt: 12.10.2026 \u00b7 Datenbasis: Airbnb-Einnahmen-Export, 44 Buchungen \u00b7 Betr\u00e4ge netto in EUR
> Phase 1: Okt\u2013Dez 2025 \u00b7 Phase 2: Mai\u2013Sep 2026 \u00b7 Zwischen den Phasen lag eine Renovierung.
> *Fassung 2 \u2013 Buchbarkeitsfenster Phase 1 korrigiert: letzte Nacht 13.12.2025 (Abreise 14.12.2025), nicht 31.12.2025.*

---

## 1. Kurzfassung

- **Der Umsatz wuchs \u00fcber die Auslastung, nicht \u00fcber den Preis.** Der Erl\u00f6s je belegter Nacht blieb praktisch konstant ({sgn(d_host)}), die Auslastung stieg von {pct(p1['ausl'])} % auf {pct(p2['ausl'])} %. Der Umsatz je *verf\u00fcgbarer* Nacht (RevPAR) stieg dadurch um {sgn((p2['revpar'] / p1['revpar'] - 1) * 100, 0)} %.
- **Airbnb hat das Geb\u00fchrenmodell gewechselt.** Aus {pct(p1['feep'],2)} % (Split Fee) wurden {pct(p2['feep'],2)} % (Host-Only Fee). Aus Vermietersicht hat sich der Airbnb-Anteil damit mehr als verf\u00fcnffacht.
- **Die Preiserh\u00f6hung war eine Kompensation, kein Gewinn.** Sie war mit {sgn(tats)} richtig bemessen, um die Geb\u00fchr auszugleichen \u2013 mehr aber auch nicht.
- **Der Gast hat kaum mehr gezahlt** ({sgn(d_gast)} je belegter Nacht). Den Zuwachs hat Airbnb abgesch\u00f6pft.
- **Konsequenz:** Der Preisspielraum ist strukturell enger geworden. Der n\u00e4chste Preisschritt muss bewusst auf die Marge zielen, nicht auf den Geb\u00fchrenausgleich.

## 2. Was sich ge\u00e4ndert hat: das Geb\u00fchrenmodell

| | Phase 1 | Phase 2 |
| --- | --- | --- |
| Modell | Split Fee | Host-Only Fee |
| Deine Geb\u00fchr | 3 % + MwSt. = **{pct(p1['feep'],2)} %** | 15,5 % + MwSt. = **{pct(p2['feep'],2)} %** |
| G\u00e4stegeb\u00fchr | 14,1\u201316,5 % \u2013 im Checkout **sichtbar** | keine \u2013 im Preis enthalten |
| Was der Gast sieht | Zimmerpreis **plus** Aufschlag | der eine, fertige Preis |
| Im Host-Export sichtbar | G\u00e4stegeb\u00fchr **nein** | entf\u00e4llt |

Die Werte f\u00fcr die eigene Geb\u00fchr sind aus den Daten gemessen (Servicegeb\u00fchr \u00f7 Bruttoeink\u00fcnfte). Die G\u00e4stegeb\u00fchr der Phase 1 steht **nicht** im Host-Export \u2013 angegeben ist der Bereich, den Airbnb im Hilfecenter nennt (Artikel 1857). Die Mehrwertsteuer ist dort laut Airbnb bereits enthalten.

## 3. Drei Preisebenen \u2013 und ihre Falle

| Ebene | Bedeutung | Phase 1 | Phase 2 |
| --- | --- | --- | --- |
| Auszahlung (netto) | was beim Vermieter ankommt | {eur(p1['adr'])} \u20ac | {eur(p2['adr'])} \u20ac |
| Listenpreis | was der Gast als Zimmerpreis sieht | {eur(p1['listen'])} \u20ac | {eur(p2['listen'])} \u20ac |
| Gast-Endpreis | was der Gast tats\u00e4chlich zahlt | ca. {eur(g1)} \u20ac | {eur(g2)} \u20ac |

> **Wichtig:** Die Spalte \u00bbBruttoeink\u00fcnfte\u00ab hei\u00dft in beiden Phasen gleich und bedeutet doch etwas anderes \u2013 in Phase 1 den Listenpreis **ohne** G\u00e4stegeb\u00fchr, in Phase 2 den **Endpreis**. Ein naiver Brutto-Vergleich \u00fcber die Phasen vergleicht zwei verschiedene Dinge.

## 4. Kennzahlen im Vergleich

| Kennzahl | Phase 1 | Phase 2 | Ver\u00e4nderung |
| --- | --- | --- | --- |
| Buchungen | {p1['n']} | {p2['n']} | \u2013 |
| Belegte N\u00e4chte | {p1['belegt']} | {p2['belegt']} | \u2013 |
| Verf\u00fcgbare N\u00e4chte | {p1['verf']} | {p2['verf']} (132 \u2212 {p2['gesperrt']} gesperrt) | \u2013 |
| **Auslastung** | {pct(p1['ausl'])} % | **{pct(p2['ausl'])} %** | {sgn(p2['ausl']-p1['ausl'])} Pp |
| Umsatz netto | {eur(p1['netto'])} \u20ac | {eur(p2['netto'])} \u20ac | {sgn((p2['netto']/p1['netto']-1)*100,0)} % |
| **ADR netto** (\u00d8 \u20ac/belegte Nacht) | {eur(p1['adr'])} \u20ac | {eur(p2['adr'])} \u20ac | {sgn(d_host)} % |
| **RevPAR** (\u00d8 \u20ac/verf\u00fcgbare Nacht) | {eur(p1['revpar'])} \u20ac | {eur(p2['revpar'])} \u20ac | {sgn((p2['revpar']/p1['revpar']-1)*100,0)} % |
| \u00d8 Aufenthalt | {pct(p1['aufenthalt'])} N\u00e4chte | {pct(p2['aufenthalt'])} N\u00e4chte | \u2013 |
| Servicegeb\u00fchr-Quote | {pct(p1['feep'],2)} % | {pct(p2['feep'],2)} % | {sgn(p2['feep']-p1['feep'])} Pp |

Die Auslastung z\u00e4hlt nur N\u00e4chte innerhalb des Buchbarkeitsfensters. In Phase 2 waren **10 N\u00e4chte gesperrt** (07.\u201316.08.2026); ohne diesen Abzug l\u00e4ge die Auslastung f\u00e4lschlich bei 84,1 % statt {pct(p2['ausl'])} %.

## 5. Der Preisvergleich je belegter Nacht

| | Phase 1 | Phase 2 | Ver\u00e4nderung |
| --- | --- | --- | --- |
| **Gast zahlt** | ca. {eur(g1)} \u20ac | {eur(g2)} \u20ac | **{sgn(d_gast)}** |
| **Du bekommst (netto)** | {eur(p1['adr'])} \u20ac | {eur(p2['adr'])} \u20ac | **{sgn(d_host)}** |
| **Airbnb bekommt** | ca. {eur(air1)} \u20ac | {eur(air2)} \u20ac | **{sgn(d_air)}** |
| Airbnb-Anteil am Gastpreis | {pct(share1)} % | {pct(share2)} % | {sgn(share2-share1)} Pp |

Der Gastpreis der Phase 1 ist eine N\u00e4herung: Der Listenpreis ist gemessen, die G\u00e4stegeb\u00fchr ist mit 15 % angesetzt (Airbnb-Band 14,1\u201316,5 %). \u00dcber das ganze Band bleibt die Aussage stabil \u2013 der Gastpreis steigt um {sgn(d_gast_lo)} bis {sgn(d_gast_hi)}, w\u00e4hrend Airbnb zwischen {sgn(d_air_lo)} und {sgn(d_air_hi)} mehr nimmt.

## 6. Warum der Preis steigen musste

Damit **dieselbe Auszahlung** herauskommt, muss der Listenpreis mit dem Faktor `(1 \u2212 {pct(p1['feep'],2)} %) / (1 \u2212 {pct(p2['feep'],2)} %)` multipliziert werden \u2013 das sind **{sgn(noetig)}**.

Tats\u00e4chlich gestiegen: **{sgn(tats)}**. Die Erh\u00f6hung war damit korrekt bemessen \u2013 sie hat die Geb\u00fchr genau kompensiert und den Netto-Erl\u00f6s stabil gehalten ({eur(p1['adr'])} \u20ac \u2192 {eur(p2['adr'])} \u20ac).

## 7. Der Multiplikator-Effekt

Jede k\u00fcnftige Netto-Erh\u00f6hung um 1 \u20ac verlangt jetzt eine Listenpreis-Erh\u00f6hung von **{pct(mult_neu,2)} \u20ac**. Vor der Umstellung waren es {pct(mult_alt,2)} \u20ac. Der Preisspielraum ist damit strukturell enger geworden \u2013 unabh\u00e4ngig von der Auslastung.

## 8. Methodik und Stolpersteine

- **Buchbarkeitsfenster.** Phase 1: 24.10.\u201313.12.2025 = 51 Tage (letzte Nacht; Abreise des letzten Gastes am 14.12.2025). Phase 2: 22.05.\u201330.09.2026 = 132 Tage \u2212 10 gesperrte = 122 verf\u00fcgbare N\u00e4chte.
- **Auslastung** nur innerhalb der Buchbarkeitsfenster; gesperrte N\u00e4chte sind abgezogen (Phase 2: 07.\u201316.08.2026).
- **Storno = Umsatz ohne Belegung.** Eine Buchung wurde storniert und trotzdem ausgezahlt: {eur(p2['storno'])} \u20ac in Phase 2. Sie z\u00e4hlt zum Umsatz, aber mit 0 belegten N\u00e4chten. Das hebt den ADR leicht an.
- **Umsatz \u2260 Belegung.** In Phase 2 stehen {p1['belegt']+p2['belegt']} belegten N\u00e4chten {p2['gebucht']+p1['gebucht']} bezahlte gegen\u00fcber (Storno + eine doppelt gebuchte Verl\u00e4ngerung).
- **G\u00e4stegeb\u00fchr Phase 1** ist nicht im Export messbar; gerechnet wird mit dem von Airbnb genannten Band 14,1\u201316,5 % (Arbeitswert 15 %).
- **Keine kausale Aussage.** Phase 1 (Herbst/Winter) und Phase 2 (Sommer) unterscheiden sich saisonal. Der Phasenvergleich zeigt den Zusammenhang, nicht die Ursache.
- **Kosten fehlen** (Nebenkosten, Reinigung, Instandhaltung) \u2013 ein Deckungsbeitrag ist daher nicht berechenbar.

## 9. Fazit

Der Sprung in Phase 2 kam aus der Nachfrage, nicht aus dem Preis: Bei {pct(p2['ausl'])} % Auslastung und praktisch unver\u00e4ndertem Netto-Preis je Nacht ist der Umsatz je verf\u00fcgbarer Nacht um {sgn((p2['revpar'] / p1['revpar'] - 1) * 100, 0)} % gestiegen. Der gleichzeitig n\u00f6tige Preisaufschlag von {sgn(tats)} diente allein dem Ausgleich der Airbnb-Geb\u00fchrenumstellung \u2013 er hat die Marge nicht erh\u00f6ht, sondern nur erhalten. Bei dieser Auslastung ist der Nachfrage-Raum vorhanden, um den Netto-Preis jetzt aktiv zu erh\u00f6hen.
"""

md_path = os.path.join(OUT, 'Phasenvergleich_Ferienwohnung.md')
pdf_path = os.path.join(OUT, 'Phasenvergleich_Ferienwohnung.pdf')

with open(md_path, 'w', encoding='utf-8') as fh:
    fh.write(md)

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-center { content: "Seite " counter(page) " von " counter(pages);
                         font-family:'DejaVu Sans'; font-size:8pt; color:#666; }
        @top-right { content: "Ferienwohnung \\2013 Phasenvergleich";
                     font-family:'DejaVu Sans'; font-size:8pt; color:#888; } }
body { font-family:'DejaVu Serif'; font-size:10.5pt; line-height:1.5; color:#111; }
h1 { font-family:'DejaVu Sans'; color:#0b4a8a; border-bottom:2px solid #0b4a8a;
     padding-bottom:4px; font-size:19pt; }
h2 { font-family:'DejaVu Sans'; color:#0b4a8a; font-size:13pt; margin-top:20px; }
h3 { font-family:'DejaVu Sans'; color:#222; font-size:11pt; }
blockquote { border-left:4px solid #0b4a8a; background:#f3f6fb; margin:10px 0;
             padding:8px 12px; font-style:italic; }
table { border-collapse:collapse; width:100%; margin:10px 0; font-size:9.5pt; }
th { background:#0b4a8a; color:#fff; text-align:left; padding:5px 7px;
     font-family:'DejaVu Sans'; }
td { border:1px solid #ccd6e4; padding:4px 7px; }
tr:nth-child(even) td { background:#f2f5fa; }
code, pre { font-family:'DejaVu Sans Mono'; background:#f4f4f4;
            border:1px solid #ddd; border-radius:4px; font-size:9pt; }
code { padding:1px 4px; }
pre { padding:8px; }
li { margin:3px 0; }
hr { border:none; border-top:1px solid #dde; margin:16px 0; }
"""

html = markdown.markdown(md, extensions=['tables', 'fenced_code'])
doc = "<html><head><meta charset='utf-8'><style>%s</style></head><body>%s</body></html>" % (CSS, html)
HTML(string=doc).write_pdf(pdf_path)

print('MD :', md_path)
print('PDF:', pdf_path, os.path.getsize(pdf_path), 'Bytes')
print()
print('P1:', {k: (round(v, 2) if isinstance(v, float) else v) for k, v in p1.items()})
print('P2:', {k: (round(v, 2) if isinstance(v, float) else v) for k, v in p2.items()})
print('Gast P1/P2: %.2f / %.2f -> %+.1f%%' % (g1, g2, d_gast))
print('Host: %+.1f%% | Airbnb %+.1f%% (Band %+.1f..%+.1f)' % (d_host, d_air, d_air_lo, d_air_hi))
print('noetig %+.1f%% vs tats %+.1f%%' % (noetig, tats))

try:
    from pypdf import PdfReader
    print('Seiten:', len(PdfReader(pdf_path).pages))
except Exception as e:
    print('Seitenzahl nicht geprueft:', e)
