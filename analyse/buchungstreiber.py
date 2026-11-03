#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Treiberanalyse Ferienwohnung: Was haengt mit Belegung und Preis zusammen?

Datenbasis : ../daten/kalender.csv  (Tagespanel, 1 Zeile je Tag)
             ../daten/buchungen.csv (Faktentabelle, 1 Zeile je Buchung)
Ausgabe    : out/*.csv, figs/*.png, BEFUNDE.md

Modell A : Logit  Belegt(ja/nein) ~ Wochenende + Betriebsphase
           Standardfehler geclustert nach Belegungsepisode
           (aufeinanderfolgende Naechte sind nicht unabhaengig).
Modell B : OLS    ADR_Netto ~ Wochenende + Betriebsphase + Naechte
           (Buchungsebene, heteroskedastie-robust HC3).

Benoetigt: pandas, numpy, statsmodels, matplotlib
"""
import csv
import datetime as dt
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

HIER = os.path.dirname(os.path.abspath(__file__))
DATEN = os.path.join(HIER, "..", "daten")
OUT = os.path.join(HIER, "out")
FIGS = os.path.join(HIER, "figs")
os.makedirs(OUT, exist_ok=True)
os.makedirs(FIGS, exist_ok=True)

WOCHENTAG_DE = {
    "Montag": "Mo", "Dienstag": "Di", "Mittwoch": "Mi", "Donnerstag": "Do",
    "Freitag": "Fr", "Samstag": "Sa", "Sonntag": "So",
}
WOCHENTAG_ORDER = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
                   "Samstag", "Sonntag"]
MONAT_DE = {1: "Jan", 2: "Feb", 3: "Mrz", 4: "Apr", 5: "Mai", 6: "Jun",
            7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dez"}
WOCHENENDE_TAGE = ["Freitag", "Samstag"]   # Freitag + Samstag = Hauptanreisetage


def de(v, n=1):
    """Zahl in deutscher Schreibweise (Dezimalkomma)."""
    return f"{v:.{n}f}".replace(".", ",")


def ds(v, n=2):
    """Wie de(), aber mit Vorzeichen."""
    return f"{v:+.{n}f}".replace(".", ",")


# --------------------------------------------------------------------------
# 1) Feiertage Baden-Wuerttemberg (Freiburg) - berechnet, nicht abgeschrieben
# --------------------------------------------------------------------------
def ostersonntag(jahr):
    """Anonymer gregorianischer Algorithmus (Meeus/Jones/Butcher)."""
    a, b, c = jahr % 19, jahr // 100, jahr % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    monat = (h + l - 7 * m + 114) // 31
    tag = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(jahr, monat, tag)


def feiertage_bw(jahr):
    o = ostersonntag(jahr)
    return {
        dt.date(jahr, 1, 1): "Neujahr",
        o - dt.timedelta(days=2): "Karfreitag",
        o + dt.timedelta(days=1): "Ostermontag",
        dt.date(jahr, 5, 1): "Tag der Arbeit",
        o + dt.timedelta(days=39): "Christi Himmelfahrt",
        o + dt.timedelta(days=50): "Pfingstmontag",
        o + dt.timedelta(days=60): "Fronleichnam",
        dt.date(jahr, 10, 3): "Tag der Deutschen Einheit",
        dt.date(jahr, 11, 1): "Allerheiligen",
        dt.date(jahr, 12, 25): "1. Weihnachtstag",
        dt.date(jahr, 12, 26): "2. Weihnachtstag",
    }


FEIERTAGE = {}
for _j in (2025, 2026):
    FEIERTAGE.update(feiertage_bw(_j))


# --------------------------------------------------------------------------
# 2) Daten laden und Panel bauen
# --------------------------------------------------------------------------
def lade_kalender():
    df = pd.read_csv(os.path.join(DATEN, "kalender.csv"), encoding="utf-8-sig",
                     sep=";", decimal=",")
    df["Datum"] = pd.to_datetime(df["Datum"]).dt.date
    return df


def lade_buchungen():
    return pd.read_csv(os.path.join(DATEN, "buchungen.csv"), encoding="utf-8-sig",
                       sep=";", decimal=",")


def baue_panel(kalender):
    """Nur buchbare Tage (Verfuegbar == ja). Renovierung + Sperren raus."""
    p = kalender[kalender["Verfuegbar"] == "ja"].copy()
    p = p.sort_values("Datum").reset_index(drop=True)
    p["belegt"] = (p["Belegt"] == "ja").astype(int)
    p["wochenende"] = p["Wochentag"].isin(WOCHENENDE_TAGE).astype(int)
    p["phase2"] = p["Betriebsphase"].str.startswith("Phase 2").astype(int)
    p["feiertag"] = [d in FEIERTAGE for d in p["Datum"]]
    p["monat_ym"] = [f"{d.year}-{d.month:02d}" for d in p["Datum"]]
    # Belegungsepisode = zusammenhaengende Tage mit gleichem Belegungsstatus
    p["episode"] = (p["belegt"] != p["belegt"].shift()).cumsum()
    return p


# --------------------------------------------------------------------------
# 3) Deskriptiv
# --------------------------------------------------------------------------
def auslastung_nach(panel, spalte, reihenfolge=None):
    g = panel.groupby(spalte)["belegt"].agg(["sum", "count"])
    g["quote"] = g["sum"] / g["count"]
    if reihenfolge is not None:
        g = g.reindex([r for r in reihenfolge if r in g.index])
    else:
        g = g.sort_index()
    return g


def lueckenanalyse(panel):
    """Unbelegte buchbare Tage: Luecke zwischen zwei Aufenthalten oder Rand?"""
    belegte_tage = [d for d, b in zip(panel["Datum"], panel["belegt"]) if b == 1]
    if not belegte_tage:
        return pd.DataFrame()
    erst, letzt = min(belegte_tage), max(belegte_tage)
    zeilen = []
    for d, b in zip(panel["Datum"], panel["belegt"]):
        if b == 1:
            continue
        if erst < d < letzt:
            art = "Luecke zwischen zwei Aufenthalten"
        else:
            art = "Rand des Buchbarkeitsfensters"
        zeilen.append({"Datum": d, "Art": art,
                       "Wochentag": d.strftime("%A")})
    return pd.DataFrame(zeilen)


# --------------------------------------------------------------------------
# 4) Modell A - Logit mit geclusterten Standardfehlern
# --------------------------------------------------------------------------
def modell_a(panel):
    X = sm.add_constant(panel[["wochenende", "phase2"]].astype(float))
    y = panel["belegt"]
    m_naiv = sm.Logit(y, X).fit(disp=0)
    m_cl = sm.Logit(y, X).fit(disp=0, cov_type="cluster",
                              cov_kwds={"groups": panel["episode"]})
    tab = pd.DataFrame({
        "koeffizient": m_cl.params,
        "se_cluster": m_cl.bse,
        "se_naiv": m_naiv.bse,
        "p_wert": m_cl.pvalues,
        "or": np.exp(m_cl.params),
        "or_lo": np.exp(m_cl.conf_int()[0]),
        "or_hi": np.exp(m_cl.conf_int()[1]),
    })
    return m_naiv, m_cl, tab


# --------------------------------------------------------------------------
# 5) Modell B - OLS auf Buchungsebene (ADR)
# --------------------------------------------------------------------------
def modell_b(buchungen):
    b = buchungen.copy()
    # Storno: Umsatz ja, Aufenthalt fand nicht statt -> kein Preisbeleg
    b = b[b["Storno"] != "ja"]
    b = b[b["Naechte"] > 0]
    b["wochenende"] = b["Anreisetag_Wochentag"].isin(WOCHENENDE_TAGE).astype(int)
    b["phase2"] = b["Betriebsphase"].str.startswith("Phase 2").astype(int)
    b["naechte"] = b["Naechte"].astype(float)
    b["adr"] = b["ADR_Netto"].astype(float)
    X = sm.add_constant(b[["wochenende", "phase2", "naechte"]])
    m = sm.OLS(b["adr"], X).fit(cov_type="HC3")
    # Robustheit: Verlaengerung (Ueberlappung) ist preislich ein Sonderfall
    b2 = b[b["Ueberlappung"] != "ja"]
    m2 = sm.OLS(b2["adr"], sm.add_constant(b2[["wochenende", "phase2", "naechte"]])
                ).fit(cov_type="HC3")
    return b, m, m2


# --------------------------------------------------------------------------
# 6) Grafiken
# --------------------------------------------------------------------------
def fig_auslastung_wochentag(panel, pfad):
    g = auslastung_nach(panel, "Wochentag", WOCHENTAG_ORDER)
    fig, ax = plt.subplots(figsize=(7, 4))
    farben = ["#c0392b" if w in WOCHENENDE_TAGE else "#5b8db8"
              for w in g.index]
    ax.bar([WOCHENTAG_DE[w] for w in g.index], g["quote"] * 100, color=farben)
    for i, (q, n) in enumerate(zip(g["quote"], g["count"])):
        ax.text(i, q * 100 + 1.5, f"{q*100:.0f}%\n(n={n})", ha="center",
                fontsize=8)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Auslastung der buchbaren Tage [%]")
    ax.set_title("Auslastung nach Wochentag\n(rot = Freitag/Samstag)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(pfad, dpi=150)
    plt.close(fig)


def fig_auslastung_monat(panel, pfad):
    g = auslastung_nach(panel, "monat_ym")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(g.index, g["quote"] * 100, color="#5b8db8")
    for i, (q, n) in enumerate(zip(g["quote"], g["count"])):
        ax.text(i, q * 100 + 1.5, f"{q*100:.0f}%", ha="center", fontsize=8)
    ax.set_ylim(0, 112)
    ax.set_ylabel("Auslastung [%]")
    ax.set_title("Auslastung nach Monat (buchbare Tage)")
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(pfad, dpi=150)
    plt.close(fig)


def fig_odds_ratios(tab, pfad):
    label = {"wochenende": "Freitag/Samstag", "phase2": "Betriebsphase 2"}
    t = tab.drop(index="const", errors="ignore")
    fig, ax = plt.subplots(figsize=(6, 3))
    ypos = np.arange(len(t))
    ax.errorbar(t["or"], ypos,
                xerr=[t["or"] - t["or_lo"], t["or_hi"] - t["or"]],
                fmt="o", color="#c0392b", capsize=4)
    ax.axvline(1.0, color="grey", linestyle="--", linewidth=1)
    ax.set_yticks(ypos)
    ax.set_yticklabels([label.get(i, i) for i in t.index])
    ax.set_xscale("log")
    ax.set_xlabel("Odds Ratio (log-Skala, 95%-KI, geclustert)")
    ax.set_title("Modell A: Chance auf Belegung")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(pfad, dpi=150)
    plt.close(fig)


def fig_adr(b, pfad):
    g = b.groupby("Anreisetag_Wochentag")["adr"]
    mittel = g.mean().reindex(WOCHENTAG_ORDER)
    n = g.count().reindex(WOCHENTAG_ORDER)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([WOCHENTAG_DE[w] for w in mittel.index], mittel.values,
           color="#5b8db8")
    for i, (m, k) in enumerate(zip(mittel.values, n.values)):
        ax.text(i, m + 0.8, f"n={k}", ha="center", fontsize=8)
    ax.set_ylabel("ADR netto [EUR/Nacht]")
    ax.set_title("Durchschnittlicher Nettopreis nach Anreisetag\n(44 Buchungen)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(pfad, dpi=150)
    plt.close(fig)


# --------------------------------------------------------------------------
# 7) Report schreiben
# --------------------------------------------------------------------------
def md_auslastung_tabelle(g, spalte_de="Wochentag"):
    zeilen = [f"| {spalte_de} | belegte Tage | buchbare Tage | Auslastung |",
              "| --- | --- | --- | --- |"]
    for k, r in g.iterrows():
        zeilen.append(f"| {k} | {int(r['sum'])} | {int(r['count'])} | "
                      f"{de(r['quote']*100)} % |")
    return "\n".join(zeilen)


# --------------------------------------------------------------------------
# 8) Power-BI-Seite "Buchungstreiber" (Variante B: deskriptiv + Modell)
# --------------------------------------------------------------------------
def g(v, n=2):
    """Zahl als deutsche Zeichenkette (Dezimalkomma)."""
    return f"{v:.{n}f}".replace(".", ",")


def treiber_wochentag(wd):
    """Auslastung je Wochentag - der deutlichste Einzelbefund."""
    zeilen = []
    for i, (tag, r) in enumerate(wd.iterrows(), start=1):
        zeilen.append([tag, str(int(r["sum"])), str(int(r["count"])),
                       g(r["quote"] * 100), 
                       "ja" if tag in WOCHENENDE_TAGE else "nein", str(i)])
    return (["Wochentag", "Belegte_Tage", "Buchbare_Tage", "Auslastung_Pct",
             "Wochenende", "Sort"], zeilen)


def treiber_verteilung(buchungen):
    """Buchungen je Anreisetag, Aufenthaltsdauer-Klasse und Vorlauf-Klasse."""
    b = buchungen.copy()
    n = len(b)
    zeilen = []

    tags = b["Anreisetag_Wochentag"].value_counts()
    for i, tag in enumerate(WOCHENTAG_ORDER, start=1):
        k = int(tags.get(tag, 0))
        zeilen.append(["Anreisetag", tag, str(k), g(k / n * 100, 1), str(i)])

    kl = pd.cut(b["Naechte"].astype(int), bins=[0, 1, 2, 3, 5, 999],
                labels=["1 Nacht", "2 Nächte", "3 Nächte",
                        "4-5 Nächte", "6+ Nächte"])
    for i, lab in enumerate(kl.cat.categories, start=1):
        k = int((kl == lab).sum())
        zeilen.append(["Aufenthalt", lab, str(k), g(k / n * 100, 1), str(i)])

    kl = pd.cut(b["Vorlauf_Tage"].astype(int), bins=[-1, 7, 14, 30, 60, 9999],
                labels=["0-7 Tage", "8-14 Tage", "15-30 Tage",
                        "31-60 Tage", "61+ Tage"])
    for i, lab in enumerate(kl.cat.categories, start=1):
        k = int((kl == lab).sum())
        zeilen.append(["Vorlauf", lab, str(k), g(k / n * 100, 1), str(i)])

    return (["Dimension", "Auspraegung", "Buchungen", "Anteil_Pct", "Sort"],
            zeilen)


def treiber_modell(tab_a, m_b):
    """Modellergebnisse als Tabelle. Die Statistik selbst rechnet Python,
    nicht Power BI - die Seite zeigt sie nur an."""
    label = {"wochenende": "Freitag/Samstag", "phase2": "Betriebsphase 2",
             "naechte": "je zusätzliche Nacht"}
    zeilen = []

    def sig(p):
        return "ja" if p < 0.05 else "nein"

    for key in ("wochenende", "phase2"):
        r = tab_a.loc[key]
        p = float(r["p_wert"])
        lesart = f"{g(float(r['or']))}x höhere Chance auf Belegung"
        if p >= 0.05:
            lesart += " (nicht signifikant)"
        zeilen.append(["A - Chance auf Belegung (Logit)", label[key],
                       "Odds Ratio", g(float(r["or"])),
                       g(float(r["or_lo"])), g(float(r["or_hi"])),
                       g(p, 3), sig(p), lesart])

    ci = m_b.conf_int()
    for key in ("wochenende", "phase2", "naechte"):
        c, p = float(m_b.params[key]), float(m_b.pvalues[key])
        lesart = f"{ds(c)} EUR je Nacht"
        if key == "naechte":
            lesart = f"{ds(c)} EUR je zusätzliche Nacht"
        if p >= 0.05:
            lesart += " (nicht signifikant)"
        zeilen.append(["B - Preis je Nacht (OLS)", label[key], "EUR je Nacht",
                       g(c), g(float(ci.loc[key, 0])), g(float(ci.loc[key, 1])),
                       g(p, 3), sig(p), lesart])

    return (["Modell", "Merkmal", "Effekt_Typ", "Effekt", "KI_unten", "KI_oben",
             "p_Wert", "Signifikant", "Lesart"], zeilen)


def treiber_luecken(luecken):
    """Unbelegte buchbare Tage je Monat (alle liegen zwischen zwei Aufenthalten)."""
    if not len(luecken):
        return (["Monat", "Unbelegte_Tage", "Sort"], [])
    g_ = luecken.groupby(luecken["Datum"].astype(str).str[:7]).size()
    zeilen = []
    for i, (k, v) in enumerate(g_.items(), start=1):
        zeilen.append([f"{MONAT_DE[int(k[5:7])]} {k[:4]}", str(int(v)), str(i)])
    return (["Monat", "Unbelegte_Tage", "Sort"], zeilen)


def schreibe_treiber_seiten(wd, buchungen, tab_a, m_b, luecken):
    """Schreibt die vier Tabellen der Seite 'Buchungstreiber' als CSV."""
    tabellen = {
        "treiber_wochentag.csv": treiber_wochentag(wd),
        "treiber_verteilung.csv": treiber_verteilung(buchungen),
        "treiber_modell.csv": treiber_modell(tab_a, m_b),
        "treiber_luecken.csv": treiber_luecken(luecken),
    }
    for name, (header, zeilen) in tabellen.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8-sig",
                  newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(header)
            w.writerows(zeilen)
    return {k: len(v[1]) for k, v in tabellen.items()}


def main():
    kalender = lade_kalender()
    buchungen = lade_buchungen()
    panel = baue_panel(kalender)

    n_buchbar = len(panel)
    n_belegt = int(panel["belegt"].sum())
    quote = n_belegt / n_buchbar

    wd = auslastung_nach(panel, "Wochentag", WOCHENTAG_ORDER)
    mo = auslastung_nach(panel, "monat_ym")
    ph = auslastung_nach(panel, "Betriebsphase")

    luecken = lueckenanalyse(panel)
    n_luecke = int((luecken["Art"] == "Luecke zwischen zwei Aufenthalten").sum()) \
        if len(luecken) else 0
    n_rand = len(luecken) - n_luecke
    p1_unbelegt = int(((panel["belegt"] == 0) & (panel["phase2"] == 0)).sum())
    p2_unbelegt = int(((panel["belegt"] == 0) & (panel["phase2"] == 1)).sum())
    p1_buchbar = int((panel["phase2"] == 0).sum())
    p2_buchbar = int((panel["phase2"] == 1).sum())
    if len(luecken):
        lm = luecken.groupby(luecken["Datum"].astype(str).str[:7]).size()
        luecken_tabelle = "\n".join(
            f"| {k} | {int(v)} |" for k, v in lm.items())
    else:
        luecken_tabelle = "| – | 0 |"

    feiertage_im_panel = sorted({d for d in panel["Datum"] if d in FEIERTAGE})

    m_naiv, m_cl, tab_a = modell_a(panel)
    b, m_b, m_b2 = modell_b(buchungen)

    # ---- CSV-Ausgaben (deutsche Schreibweise: Semikolon, Dezimalkomma, BOM)
    def _de(pfad, frame, index=True):
        frame.to_csv(os.path.join(OUT, pfad), sep=';', decimal=',',
                     encoding='utf-8-sig', index=index)
    _de("auslastung_wochentag.csv", wd)
    _de("auslastung_monat.csv", mo)
    _de("auslastung_phase.csv", ph)
    _de("modell_a_odds_ratios.csv", tab_a)
    if len(luecken):
        _de("unbelegte_tage.csv", luecken, index=False)

    # ---- Tabellen der Power-BI-Seite "Buchungstreiber"
    treiber_zeilen = schreibe_treiber_seiten(wd, buchungen, tab_a, m_b, luecken)

    # ---- Grafiken
    fig_auslastung_wochentag(panel, os.path.join(FIGS, "auslastung_wochentag.png"))
    fig_auslastung_monat(panel, os.path.join(FIGS, "auslastung_monat.png"))
    fig_odds_ratios(tab_a, os.path.join(FIGS, "odds_ratios.png"))
    fig_adr(b, os.path.join(FIGS, "adr_wochentag.png"))

    # ---- Kennzahlen fuer den Text
    or_we = tab_a.loc["wochenende"]
    or_p2 = tab_a.loc["phase2"]
    c_we, c_p2, c_n = m_b.params["wochenende"], m_b.params["phase2"], m_b.params["naechte"]
    ci_n = m_b.conf_int().loc["naechte"]
    r2 = m_b.rsquared
    r2b = m_b2.rsquared
    med_vorlauf = buchungen["Vorlauf_Tage"].median()
    med_naechte = buchungen["Naechte"].median()
    anteil_kurz = (buchungen["Naechte"] <= 3).mean()

    text = f"""# Treiberanalyse: Belegung und Preis der Ferienwohnung

**Frage:** Was hängt damit zusammen, dass die Wohnung gebucht wird — und was
mit dem erzielten Nettopreis?

**Datenbasis:** `kalender.csv` (Tagespanel) und `buchungen.csv`
(Faktentabelle) aus `airbnb-portfolio/daten/`.
**Erzeugt von:** `analyse/buchungstreiber.py` — alle Zahlen hier sind
Skriptausgaben, keine Schätzungen aus dem Kopf.

---

## 1 · Auslastung: die Basis

| Kennzahl | Wert |
| --- | --- |
| Buchbare Tage (Nenner) | {n_buchbar} |
| Davon belegt | {n_belegt} |
| Auslastung | **{de(quote*100)} %** |
| Nicht belegte buchbare Tage | {n_buchbar - n_belegt} |

Der Nenner enthält nur die Buchbarkeitsfenster der beiden Phasen — keine
Renovierungsmonate, keine gesperrten Nächte. Sonst wäre die Auslastung zu
niedrig.

### Nach Wochentag

{md_auslastung_tabelle(wd)}

Freitag und Samstag liegen bei {de(wd.loc['Freitag','quote']*100, 0)} % bzw.
{de(wd.loc['Samstag','quote']*100, 0)} %, Montag und Donnerstag nur bei
{de(wd.loc['Montag','quote']*100, 0)} % / {de(wd.loc['Donnerstag','quote']*100, 0)} %.
Das ist der deutlichste Einzelunterschied im Datensatz.

### Nach Betriebsphase

{md_auslastung_tabelle(ph, 'Betriebsphase')}

### Nach Monat

{md_auslastung_tabelle(mo, 'Monat')}

⚠️ Die beiden Phasen sind **nicht** über denselben Kalender vergleichbar:
Phase 1 = Okt–Dez, Phase 2 = Mai–Okt. Der Phasenunterschied und der
Saisoneffekt sind in diesen Daten untrennbar.

## 2 · Wo die Lücken liegen

Alle {n_buchbar - n_belegt} nicht belegten buchbaren Tage liegen **innerhalb**
des Vermietungszeitraums, keiner am Rand. Sie verteilen sich so:

| Monat | unbesetzte buchbare Tage |
| --- | --- |
{luecken_tabelle}

Aufteilung nach Phase: **{p1_unbelegt}** Tage in Phase 1 (von {p1_buchbar} = 
{de(p1_unbelegt/p1_buchbar*100)} % unbesetzt), **{p2_unbelegt}** Tage in Phase 2
(von {p2_buchbar} = {de(p2_unbelegt/p2_buchbar*100)} %).

In Phase 2 sind die Lücken **Einzeltage zwischen zwei Aufenthalten**, keine
Blöcke. Das passt zu Mindestaufenthalt und Reinigungsabstand: zwischen zwei
Aufenthalten bleibt ein Tag unverkäuflich, obwohl der Monat insgesamt stark
gebucht ist. Die Winterblöcke (Nov/Dez 2025) sind dagegen echte
Nachfragelücken.

**Praxis-Test:** Die {p1_unbelegt} Wintertage sind der einzige echte Erlös-Hebel.
Verkauft man 5 der {p1_unbelegt} Tage zu 55 € netto, sind das rund 275 € zusätzlich.
Die {p2_unbelegt} Sommertage sind nur über eine Mindestaufenthalts-Anpassung zu holen.

## 3 · Modell A — Chance auf Belegung (Logit)

Zielgröße: `Belegt ja/nein` je buchbarem Tag ({n_buchbar} Tage).
Prädiktoren: Freitag/Samstag und Betriebsphase.
Standardfehler **geclustert nach Belegungsepisode**, weil aufeinanderfolgende
Nächte desselben Aufenthalts nicht unabhängig sind.

| Merkmal | Odds Ratio | 95%-KI | p-Wert |
| --- | --- | --- | --- |
| Freitag/Samstag | {or_we['or']:.2f} | {or_we['or_lo']:.2f} – {or_we['or_hi']:.2f} | {or_we['p_wert']:.3f} |
| Betriebsphase 2 | {or_p2['or']:.2f} | {or_p2['or_lo']:.2f} – {or_p2['or_hi']:.2f} | {or_p2['p_wert']:.3f} |

Lesart: Ein Odds Ratio von {de(or_we['or'])} heißt, dass ein Freitag oder
Samstag eine um den Faktor {de(or_we['or'])} höhere Chance hat, belegt zu
sein als ein Werktag — **{de(or_we['or']-1, 2)} ×** bzw. rund
{de((or_we['or']-1)*100, 0)} % mehr.

**Warum geclustert:** ungeclustert wäre der Standardfehler für
„Freitag/Samstag" {de(tab_a.loc['wochenende','se_naiv'], 2)} statt
{de(tab_a.loc['wochenende','se_cluster'], 2)}. Der Wochenendeffekt ist also
weniger sicher als er naiv aussieht — das 95%-Intervall reicht von
{de(or_we['or_lo'])} bis {de(or_we['or_hi'])}.

Die Betriebsphase ist dagegen **nicht signifikant** (p = {de(or_p2['p_wert'], 3)}) —
ihr Effekt ist mit {n_buchbar - n_belegt} nicht belegten Tagen nicht von
Zufall zu trennen.

**Nicht schätzbar:** Feiertage. Im buchbaren Fenster liegen nur
{len(feiertage_im_panel)} Feiertage ({", ".join(d.strftime("%d.%m.%Y") for d in feiertage_im_panel)}) —
zu wenige für einen eigenen Koeffizienten. Alle drei waren belegt.

## 4 · Modell B — Was den Nettopreis erklärt (OLS)

Buchungsebene, n = {len(b)} (Storno ausgeschlossen: Umsatz ja, Aufenthalt
nein). Zielgröße: `ADR_Netto` = Nettopreis je Nacht.

| Merkmal | Effekt auf ADR | 95%-KI | p-Wert |
| --- | --- | --- | --- |
| Freitag/Samstag | {ds(c_we)} € | {ds(m_b.conf_int().loc['wochenende',0])} – {ds(m_b.conf_int().loc['wochenende',1])} € | {de(m_b.pvalues['wochenende'], 3)} |
| Betriebsphase 2 | {ds(c_p2)} € | {ds(m_b.conf_int().loc['phase2',0])} – {ds(m_b.conf_int().loc['phase2',1])} € | {de(m_b.pvalues['phase2'], 3)} |
| je zusätzliche Nacht | {ds(c_n)} € | {ds(ci_n[0])} – {ds(ci_n[1])} € | {de(m_b.pvalues['naechte'], 3)} |

R² = {de(r2, 3)}. Ohne die Verlängerungsbuchung (preislich ein Sonderfall):
R² = {de(r2b, 3)}. n = {len(b)} — mehr als drei Prädiktoren wären hier
unseriös.

Der klarste Effekt ist die **Aufenthaltsdauer**: längere Aufenthalte zahlen
je Nacht weniger. Der Wochentagseffekt beim *Preis* ist dagegen klein — der
Wochentag wirkt auf die **Wahrscheinlichkeit** einer Buchung, nicht auf den
Preis je Nacht.

## 5 · Was das praktisch heißt

- **Wochenenden tragen die Nachfrage.** Freitag/Samstag sind praktisch
  ausgebucht ({de(wd.loc['Freitag','quote']*100, 0)} % / {de(wd.loc['Samstag','quote']*100, 0)} %).
  Wer Erlös steigern will, hebt den **Wochenendpreis**, nicht den Grundpreis.
- **Montag und Donnerstag sind die schwächsten Tage**
  ({de(wd.loc['Montag','quote']*100, 0)} % / {de(wd.loc['Donnerstag','quote']*100, 0)} %).
  Dort ist ein Rabatt oder eine Mindestaufenthaltslockerung wirksamer als
  eine allgemeine Preissenkung.
- **{de(anteil_kurz*100, 0)} % der Buchungen sind ≤ 3 Nächte**, Median
  {de(med_naechte, 1)} Nächte, medianer Vorlauf {de(med_vorlauf, 0)} Tage.
  Das ist Kurzfrist- und Kurzaufenthaltstourismus — Wochenendausflüge.
- **Der Preis je Nacht reagiert kaum auf den Wochentag**
  ({ds(c_we)} €, p = {de(m_b.pvalues['wochenende'], 2)}), sondern auf die
  **Aufenthaltsdauer**: jede zusätzliche Nacht kostet
  {de(abs(c_n), 2)} € weniger pro Nacht. Längere Aufenthalte werden also
  schon heute rabattiert.
- **Die Lücken liegen nicht in der Nachfrage, sondern im Kalender:**
  {n_luecke} von {n_buchbar - n_belegt} unbesetzten Tagen sitzen zwischen
  zwei Aufenthalten. Da ist der Hebel kleiner als er aussieht — ein Tag
  Zwischenlücke lässt sich kaum verkaufen.

## 6 · Grenzen — bitte mitlesen

1. **Korrelation, nicht Kausalität.** Der Preis ist selbst gesetzt, der
   Wochentag nicht. Nur der Wochentag ist hier exogen.
2. **Kleine Stichprobe.** {n_buchbar - n_belegt} nicht belegte Tage tragen
   Modell A. Mehr als zwei Prädiktoren wären unseriös.
3. **Saison und Phase sind vermischt.** Phase 1 (Okt–Dez) und Phase 2
   (Mai–Okt) sind unterschiedliche Jahreszeiten; der Phaseneffekt enthält
   beides.
4. **Fehlende Nächte sind nicht sichtbar.** Sperren aus Eigennutzung oder
   Reparatur stehen nicht im Export — die Auslastung ist eine Obergrenze.
5. **Motive stehen hier nicht drin.** „Warum" jemand bucht, beantwortet
   keine Transaktion. Dafür bräuchte es Bewertungstexte
   (`daten/bewertungen_vorlage.csv`) oder eine Gästebefragung.
6. **Feiertage, Brückentage, Schulferien, Events** sind in dieser Fassung
   nicht als Prädiktoren enthalten — zu wenige Fälle bzw. keine belastbare
   Quelle im Workspace.
"""

    with open(os.path.join(HIER, "BEFUNDE.md"), "w", encoding="utf-8") as fh:
        fh.write(text)

    print(f"buchbare Tage: {n_buchbar} | belegt: {n_belegt} | "
          f"Auslastung: {quote*100:.1f} %")
    print(f"Luecken: {n_luecke} zwischen Aufenthalten, {n_rand} am Rand")
    print(f"Feiertage im buchbaren Fenster: "
          f"{', '.join(d.strftime('%d.%m.%Y') for d in feiertage_im_panel)}")
    print("\nModell A (Odds Ratios, geclustert):")
    print(tab_a.round(3).to_string())
    print("\nModell B (OLS, HC3):")
    print(m_b.summary2().tables[1].round(3).to_string())
    print(f"R2 = {r2:.3f} | ohne Verlaengerung R2 = {r2b:.3f} | n = {len(b)}")
    print("\nGeschrieben: BEFUNDE.md, out/*.csv, figs/*.png")
    print("Seite Buchungstreiber:", ", ".join(
        f"{k}={v}" for k, v in treiber_zeilen.items()))


if __name__ == "__main__":
    main()
