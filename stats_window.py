"""Fenêtre Statistiques — PyQt6 + Matplotlib."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

from config import MODULES
from db import queries

# ── Palette ──────────────────────────────────────────────────────────────────

_C_VALIDE   = "#21c354"
_C_ATTENTE  = "#1f497d"
_C_PRECHECK = "#f59e0b"
_C_ENCOURS  = "#d1d5db"
_C_BG       = "#f8f9fa"
_C_CARD_BG  = "#ffffff"
_C_TEXT     = "#1f2937"

_COMPLEXITY_WEIGHTS = {
    "n_deca": 0.20, "n_pn": 0.15, "n_complex": 0.35,
    "n_svc3_distinct": 0.15, "n_svc4_internal": 0.15,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_figure(tight=True) -> tuple[Figure, any]:
    fig = Figure(facecolor=_C_BG)
    ax  = fig.add_subplot(111)
    ax.set_facecolor(_C_BG)
    if tight:
        fig.tight_layout(pad=1.5)
    return fig, ax


def _canvas(fig: Figure) -> FigureCanvasQTAgg:
    c = FigureCanvasQTAgg(fig)
    c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    return c


def _card(value: str, label: str, color: str = _C_TEXT) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.StyledPanel)
    f.setStyleSheet(f"QFrame {{ background:{_C_CARD_BG}; border-radius:8px; border:1px solid #e5e7eb; }}")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    v = QLabel(value)
    v.setAlignment(Qt.AlignmentFlag.AlignCenter)
    v.setStyleSheet(f"font-size:26px; font-weight:bold; color:{color}; border:none;")
    l = QLabel(label)
    l.setAlignment(Qt.AlignmentFlag.AlignCenter)
    l.setStyleSheet("font-size:11px; color:#6b7280; border:none;")
    lay.addWidget(v)
    lay.addWidget(l)
    return f


def _section(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size:14px; font-weight:bold; color:#1f2937; padding-top:8px;")
    return lbl


def _ro_item(text: str, bg: str | None = None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    if bg:
        it.setBackground(QColor(bg))
    return it


# ── Onglet 1 — Vue d'ensemble ────────────────────────────────────────────────

class _OverviewTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(12)
        self._build()

    def _build(self):
        # Vider au refresh
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        stats_rows = queries.get_all_stats_all_modules(MODULES)
        if not stats_rows:
            self._lay.addWidget(QLabel("Aucune donnée en base."))
            return

        df = pd.DataFrame(stats_rows)
        total_g    = int(df["total"].sum())
        valide_g   = int(df["valide"].sum())
        attente_g  = int(df["en_attente"].sum())
        precheck_g = int(df["precheck"].sum())
        encours_g  = int(df["en_cours"].sum())
        traites_g  = valide_g + attente_g
        pct_g      = round(100 * traites_g / total_g) if total_g else 0

        # ── Cartes KPI ────────────────────────────────────────────────────────
        row = QHBoxLayout()
        row.addWidget(_card(str(total_g),    "Total DECAs",   _C_TEXT))
        row.addWidget(_card(str(valide_g),   "Validés",       _C_VALIDE))
        row.addWidget(_card(str(attente_g),  "En attente",    _C_ATTENTE))
        row.addWidget(_card(str(precheck_g), "Pré-check",     _C_PRECHECK))
        row.addWidget(_card(str(encours_g),  "En cours",      "#9ca3af"))
        row.addWidget(_card(f"{pct_g}%",     "Traités",       _C_VALIDE if pct_g == 100 else _C_TEXT))
        self._lay.addLayout(row)

        # ── Graphique barres empilées par module ───────────────────────────────
        self._lay.addWidget(_section("Avancement par module"))

        modules  = df["module"].tolist()
        valides  = df["valide"].tolist()
        attentes = df["en_attente"].tolist()
        prechecks= df["precheck"].tolist()
        encours  = df["en_cours"].tolist()
        totals   = df["total"].tolist()

        fig = Figure(facecolor=_C_BG, figsize=(10, max(3, len(modules) * 0.55 + 1)))
        ax  = fig.add_subplot(111)
        ax.set_facecolor(_C_BG)

        y = range(len(modules))
        bar_h = 0.55

        b1 = ax.barh(list(y), valides,  bar_h, color=_C_VALIDE,  label="Validé")
        b2 = ax.barh(list(y), attentes, bar_h, left=valides,      color=_C_ATTENTE, label="En attente")
        left2 = [v + a for v, a in zip(valides, attentes)]
        b3 = ax.barh(list(y), prechecks,bar_h, left=left2,        color=_C_PRECHECK,label="Pré-check")
        left3 = [l + p for l, p in zip(left2, prechecks)]
        b4 = ax.barh(list(y), encours,  bar_h, left=left3,        color=_C_ENCOURS, label="En cours")

        # Labels % dans chaque barre
        for i, (v, a, p, e, t) in enumerate(zip(valides, attentes, prechecks, encours, totals)):
            pct = round(100 * (v + a) / t) if t else 0
            ax.text(t + t * 0.01, i, f"{pct}%", va="center", fontsize=8, color=_C_TEXT)

        ax.set_yticks(list(y))
        ax.set_yticklabels(modules, fontsize=9)
        ax.set_xlabel("DECAs", fontsize=9)
        ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
        ax.legend(loc="lower right", fontsize=8, framealpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_xlim(0, max(totals) * 1.12 if totals else 1)
        fig.tight_layout(pad=1.5)

        cv = _canvas(fig)
        cv.setMinimumHeight(max(180, len(modules) * 38 + 60))
        self._lay.addWidget(cv)

        # ── Tableau complexité ────────────────────────────────────────────────
        self._lay.addWidget(_section("Charge estimée par module (score de complexité)"))

        cx_rows = []
        for m in MODULES:
            c = queries.get_complexity_stats_for_module(m)
            if not c or c.get("n_deca", 0) == 0:
                continue
            s = queries.get_stats_for_module(m)
            traites = s.get("valide", 0) + s.get("en_attente", 0)
            restant = max(0, c["n_deca"] - traites)
            cx_rows.append({
                "module": m, "restant": restant,
                "_n_deca": c["n_deca"], "_n_pn": c["n_pn"],
                "_n_complex": c["n_complex"],
                "_n_svc3": c["n_svc3_distinct"],
                "_n_svc4i": c["n_svc4_internal"],
                "n_ext": c["n_ext_storage"],
            })

        if cx_rows:
            df_cx = pd.DataFrame(cx_rows)
            for col in ("_n_deca", "_n_pn", "_n_complex", "_n_svc3", "_n_svc4i"):
                mx = df_cx[col].max() or 1
                df_cx[col] = df_cx[col] / mx
            df_cx["score"] = (
                df_cx["_n_deca"]    * _COMPLEXITY_WEIGHTS["n_deca"] +
                df_cx["_n_pn"]      * _COMPLEXITY_WEIGHTS["n_pn"] +
                df_cx["_n_complex"] * _COMPLEXITY_WEIGHTS["n_complex"] +
                df_cx["_n_svc3"]    * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
                df_cx["_n_svc4i"]   * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
            )
            df_cx["Score"] = (df_cx["score"] * 4 + 1).round(1)
            df_cx = df_cx.sort_values("Score", ascending=False).reset_index(drop=True)

            headers = ["Module", "Restants", "Score /5", "Cas complexes", "Svc3 ≠", "Svc4 ≠ int.", "Stk ext."]
            tbl = QTableWidget(len(df_cx), len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.setMaximumHeight(min(260, 36 + len(df_cx) * 30))
            tbl.setAlternatingRowColors(True)

            original = cx_rows  # to get raw values
            orig_map = {r["module"]: r for r in cx_rows}
            for i, row in df_cx.iterrows():
                m = cx_rows[0]["module"] if len(cx_rows) == 1 else None
                # Find original row by score order
                orig = orig_map.get(df_cx.at[i, "module"] if "module" in df_cx.columns else "", {})
                # We kept module in df_cx
                stars = ("★" * int(row["Score"])).ljust(5, "☆")
                score_str = f"{row['Score']:.1f}  {stars}"
                vals = [
                    df_cx.at[i, "module"] if "module" in df_cx.columns else "",
                    str(int(cx_rows[i]["restant"])),
                    score_str,
                    str(int(cx_rows[i]["_n_complex"] * (df_cx["_n_complex"].max() * (cx_rows[i].get("_n_complex_raw", 0) or 1)))) if False else "",
                ]
                # simpler: just use the original cx_rows in order
                pass

            # Re-build more simply
            tbl.setRowCount(0)
            orig_list = sorted(cx_rows, key=lambda r: -(
                (r["_n_deca"] / (max(x["_n_deca"] for x in cx_rows) or 1)) * _COMPLEXITY_WEIGHTS["n_deca"] +
                (r["_n_pn"]   / (max(x["_n_pn"]   for x in cx_rows) or 1)) * _COMPLEXITY_WEIGHTS["n_pn"] +
                (r["_n_complex"]/(max(x["_n_complex"] for x in cx_rows) or 1)) * _COMPLEXITY_WEIGHTS["n_complex"] +
                (r["_n_svc3"] / (max(x["_n_svc3"]   for x in cx_rows) or 1)) * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
                (r["_n_svc4i"]/ (max(x["_n_svc4i"]  for x in cx_rows) or 1)) * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
            ))
            mx = {k: max((x[k] for x in cx_rows), default=1) or 1
                  for k in ("_n_deca","_n_pn","_n_complex","_n_svc3","_n_svc4i")}
            for r in orig_list:
                sc = (
                    (r["_n_deca"]   /mx["_n_deca"])   * _COMPLEXITY_WEIGHTS["n_deca"] +
                    (r["_n_pn"]     /mx["_n_pn"])      * _COMPLEXITY_WEIGHTS["n_pn"] +
                    (r["_n_complex"]/mx["_n_complex"]) * _COMPLEXITY_WEIGHTS["n_complex"] +
                    (r["_n_svc3"]   /mx["_n_svc3"])    * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
                    (r["_n_svc4i"]  /mx["_n_svc4i"])   * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
                ) * 4 + 1
                stars = "★" * round(sc) + "☆" * (5 - round(sc))
                row_i = tbl.rowCount()
                tbl.insertRow(row_i)
                tbl.setRowHeight(row_i, 28)
                for col_i, val in enumerate([
                    r["module"],
                    str(r["restant"]),
                    f"{sc:.1f}  {stars}",
                    str(r["_n_complex"]),
                    str(r["_n_svc3"]),
                    str(r["_n_svc4i"]),
                    str(r["n_ext"]),
                ]):
                    tbl.setItem(row_i, col_i, _ro_item(val))

            self._lay.addWidget(tbl)

        self._lay.addStretch()

    def refresh(self):
        self._build()


# ── Onglet 2 — Activité ──────────────────────────────────────────────────────

class _ActivityTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        self._lay = lay
        self._build()

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        rows = queries.get_activity_by_day()
        if not rows:
            self._lay.addWidget(QLabel("Aucune activité enregistrée."))
            self._lay.addStretch()
            return

        df = pd.DataFrame([dict(r) for r in rows])
        df["day"] = pd.to_datetime(df["day"])
        df = df.sort_values("day").reset_index(drop=True)
        df["cumul"] = df["n"].cumsum()

        total_decisions = int(df["n"].sum())
        n_jours = max((df["day"].iloc[-1] - df["day"].iloc[0]).days, 1)
        vitesse = total_decisions / n_jours  # décisions/jour

        # Vitesse des 7 derniers jours
        cutoff = df["day"].max() - pd.Timedelta(days=7)
        recent = df[df["day"] >= cutoff]
        vitesse_rec = recent["n"].sum() / 7 if not recent.empty else vitesse

        # Estimation de fin
        total_deca = sum(s.get("total", 0) for s in [queries.get_stats_for_module(m) for m in MODULES])
        traites    = sum(s.get("valide", 0) + s.get("en_attente", 0)
                         for s in [queries.get_stats_for_module(m) for m in MODULES])
        restant    = max(0, total_deca - traites)
        if vitesse_rec > 0:
            jours_restants = int(restant / vitesse_rec)
            date_fin = datetime.now() + timedelta(days=jours_restants)
            eta_str  = date_fin.strftime("%d/%m/%Y") + f"  ({jours_restants} j)"
        else:
            eta_str = "—"

        # KPI cards
        kpi_row = QHBoxLayout()
        kpi_row.addWidget(_card(str(total_decisions), "Décisions posées (total)"))
        kpi_row.addWidget(_card(f"{vitesse:.1f}/j",    "Vitesse moyenne globale"))
        kpi_row.addWidget(_card(f"{vitesse_rec:.1f}/j","Vitesse (7 derniers jours)", _C_VALIDE))
        kpi_row.addWidget(_card(str(restant),          "DECAs restants",             "#e74c3c" if restant else _C_VALIDE))
        kpi_row.addWidget(_card(eta_str,               "Estimation de fin",          _C_ATTENTE))
        self._lay.addLayout(kpi_row)

        # Graphique : courbe cumulative + barres quotidiennes
        self._lay.addWidget(_section("Activité journalière et progression cumulée"))

        fig = Figure(facecolor=_C_BG, figsize=(10, 4))
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()
        ax1.set_facecolor(_C_BG)
        ax2.set_facecolor(_C_BG)

        ax1.bar(df["day"], df["n"], color=_C_PRECHECK, alpha=0.6, label="Décisions/jour")
        ax2.plot(df["day"], df["cumul"], color=_C_VALIDE, linewidth=2.5, label="Cumulé")
        ax2.fill_between(df["day"], df["cumul"], alpha=0.08, color=_C_VALIDE)

        # Ligne ETA
        if vitesse_rec > 0 and restant > 0:
            ax2.axhline(total_deca, color="#e74c3c", linestyle="--", linewidth=1, alpha=0.6)
            ax2.text(df["day"].iloc[-1], total_deca * 1.01, f"  Objectif : {total_deca}", fontsize=8, color="#e74c3c")

        ax1.set_xlabel("Date", fontsize=9)
        ax1.set_ylabel("Décisions/jour", fontsize=9, color=_C_PRECHECK)
        ax2.set_ylabel("Cumulé", fontsize=9, color=_C_VALIDE)
        ax1.spines["top"].set_visible(False)
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper left")
        fig.autofmt_xdate(rotation=30, ha="right")
        fig.tight_layout(pad=1.5)

        self._lay.addWidget(_canvas(fig))

        # Histogramme par semaine
        self._lay.addWidget(_section("Activité par semaine"))
        df["week"] = df["day"].dt.to_period("W").apply(lambda p: p.start_time)
        df_w = df.groupby("week")["n"].sum().reset_index()
        df_w["week_lbl"] = df_w["week"].dt.strftime("S%W\n%d/%m")

        fig2 = Figure(facecolor=_C_BG, figsize=(10, 3))
        ax3  = fig2.add_subplot(111)
        ax3.set_facecolor(_C_BG)
        ax3.bar(range(len(df_w)), df_w["n"], color=_C_ATTENTE, alpha=0.85)
        ax3.set_xticks(range(len(df_w)))
        ax3.set_xticklabels(df_w["week_lbl"], fontsize=8)
        ax3.set_ylabel("Décisions", fontsize=9)
        ax3.spines["top"].set_visible(False)
        ax3.spines["right"].set_visible(False)
        for i, v in enumerate(df_w["n"]):
            ax3.text(i, v + 0.3, str(v), ha="center", fontsize=8)
        fig2.tight_layout(pad=1.5)
        self._lay.addWidget(_canvas(fig2))

        self._lay.addStretch()

    def refresh(self):
        self._build()


# ── Onglet 3 — Distributions ─────────────────────────────────────────────────

class _DistribTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        self._lay = lay
        self._build()

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        # Statut global (pie)
        all_stats = [queries.get_stats_for_module(m) for m in MODULES]
        valide_g   = sum(s.get("valide", 0)     for s in all_stats)
        attente_g  = sum(s.get("en_attente", 0) for s in all_stats)
        precheck_g = sum(s.get("precheck", 0)   for s in all_stats)
        encours_g  = sum(s.get("en_cours", 0)   for s in all_stats)

        self._lay.addWidget(_section("Répartition des statuts (global)"))
        fig_pie = Figure(facecolor=_C_BG, figsize=(5, 3.5))
        ax_pie  = fig_pie.add_subplot(111)
        ax_pie.set_facecolor(_C_BG)
        vals   = [valide_g, attente_g, precheck_g, encours_g]
        labels = ["Validé", "En attente", "Pré-check", "En cours"]
        colors = [_C_VALIDE, _C_ATTENTE, _C_PRECHECK, _C_ENCOURS]
        non_zero = [(v, l, c) for v, l, c in zip(vals, labels, colors) if v > 0]
        if non_zero:
            v2, l2, c2 = zip(*non_zero)
            wedges, texts, autotexts = ax_pie.pie(
                v2, labels=l2, colors=c2, autopct="%1.0f%%",
                startangle=90, pctdistance=0.78,
            )
            for at in autotexts:
                at.set_fontsize(9)
            ax_pie.set_title("Statuts", fontsize=10, pad=4)
        fig_pie.tight_layout(pad=1.0)

        half = QHBoxLayout()
        half.addWidget(_canvas(fig_pie))

        # N.Service 3 distribution (top 15)
        svc3_rows = queries.get_svc3_distribution()
        if svc3_rows:
            df3 = pd.DataFrame([dict(r) for r in svc3_rows]).head(15)
            fig3 = Figure(facecolor=_C_BG, figsize=(7, max(3, len(df3) * 0.45 + 1)))
            ax3  = fig3.add_subplot(111)
            ax3.set_facecolor(_C_BG)
            labels3 = [str(v)[:35] for v in df3["n_service3"]]
            ax3.barh(labels3, df3["n"], color=_C_VALIDE, alpha=0.85)
            for i, v in enumerate(df3["n"]):
                ax3.text(v + 0.2, i, str(v), va="center", fontsize=8)
            ax3.set_title("Top N.Service 3 assignés", fontsize=10)
            ax3.set_xlabel("Occurrences", fontsize=9)
            ax3.spines["top"].set_visible(False)
            ax3.spines["right"].set_visible(False)
            ax3.invert_yaxis()
            fig3.tight_layout(pad=1.5)
            half.addWidget(_canvas(fig3), stretch=2)

        self._lay.addLayout(half)

        # N.Service 4 distribution
        svc4_rows = queries.get_svc4_distribution()
        if svc4_rows:
            self._lay.addWidget(_section("Distribution N.Service 4"))
            df4 = pd.DataFrame([dict(r) for r in svc4_rows]).head(20)
            fig4 = Figure(facecolor=_C_BG, figsize=(10, max(3, len(df4) * 0.42 + 1)))
            ax4  = fig4.add_subplot(111)
            ax4.set_facecolor(_C_BG)
            labels4 = [str(v)[:40] for v in df4["n_service4"]]
            ax4.barh(labels4, df4["n"], color=_C_ATTENTE, alpha=0.85)
            for i, v in enumerate(df4["n"]):
                ax4.text(v + 0.2, i, str(v), va="center", fontsize=8, color="white" if v > 5 else _C_TEXT)
            ax4.set_title("Top N.Service 4 assignés", fontsize=10)
            ax4.set_xlabel("Occurrences", fontsize=9)
            ax4.spines["top"].set_visible(False)
            ax4.spines["right"].set_visible(False)
            ax4.invert_yaxis()
            fig4.tight_layout(pad=1.5)
            cv4 = _canvas(fig4)
            cv4.setMinimumHeight(max(200, len(df4) * 25 + 60))
            self._lay.addWidget(cv4)

        # PN partagés vs exclusifs
        self._lay.addWidget(_section("PNs exclusifs vs partagés par module"))
        pn_rows = []
        for m in MODULES:
            p = queries.get_pn_stats_for_module(m)
            if p.get("n_pn_total", 0):
                excl   = p.get("n_pn_exclusive", 0)
                shared = p.get("n_pn_total", 0) - excl
                pn_rows.append({"module": m, "exclusifs": excl, "partagés": shared})
        if pn_rows:
            df_pn = pd.DataFrame(pn_rows)
            fig5 = Figure(facecolor=_C_BG, figsize=(10, max(3, len(df_pn) * 0.55 + 1)))
            ax5  = fig5.add_subplot(111)
            ax5.set_facecolor(_C_BG)
            y5 = range(len(df_pn))
            ax5.barh(list(y5), df_pn["exclusifs"], 0.5, color=_C_VALIDE,  label="Exclusifs")
            ax5.barh(list(y5), df_pn["partagés"],  0.5, left=df_pn["exclusifs"], color=_C_PRECHECK, label="Partagés")
            ax5.set_yticks(list(y5))
            ax5.set_yticklabels(df_pn["module"], fontsize=9)
            ax5.legend(fontsize=8)
            ax5.spines["top"].set_visible(False)
            ax5.spines["right"].set_visible(False)
            ax5.set_xlabel("Nombre de PNs", fontsize=9)
            fig5.tight_layout(pad=1.5)
            self._lay.addWidget(_canvas(fig5))

        self._lay.addStretch()

    def refresh(self):
        self._build()


# ── Onglet 4 — Historique ────────────────────────────────────────────────────

class _HistoriqueTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Filtres
        fil = QHBoxLayout()
        self._mod_cb = QComboBox()
        self._mod_cb.addItems(["Tous les modules"] + MODULES)
        self._mod_cb.setFixedWidth(160)
        fil.addWidget(QLabel("Module :"))
        fil.addWidget(self._mod_cb)
        fil.addSpacing(12)

        self._marq_ed = QLineEdit()
        self._marq_ed.setPlaceholderText("Marquage…")
        self._marq_ed.setFixedWidth(130)
        fil.addWidget(QLabel("Marquage :"))
        fil.addWidget(self._marq_ed)
        fil.addSpacing(12)

        self._period_cb = QComboBox()
        self._period_cb.addItems(["Tout", "7 derniers jours", "30 derniers jours", "Aujourd'hui"])
        self._period_cb.setFixedWidth(160)
        fil.addWidget(QLabel("Période :"))
        fil.addWidget(self._period_cb)
        fil.addSpacing(12)

        btn_search = QPushButton("Actualiser")
        btn_search.setFixedHeight(28)
        btn_search.clicked.connect(self._load)
        fil.addWidget(btn_search)

        self._btn_export = QPushButton("⬇ Export CSV")
        self._btn_export.setFixedHeight(28)
        self._btn_export.clicked.connect(self._export_csv)
        fil.addWidget(self._btn_export)
        fil.addStretch()
        lay.addLayout(fil)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(self._lbl_count)

        # Table
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(7)
        self._tbl.setHorizontalHeaderLabels(
            ["Date", "Marquage", "PN", "Champ", "Ancienne valeur", "Nouvelle valeur", "Par"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._tbl.setColumnWidth(0, 145)
        self._tbl.setColumnWidth(1, 100)
        self._tbl.setColumnWidth(2, 90)
        self._tbl.setColumnWidth(3, 70)
        self._tbl.setColumnWidth(4, 150)
        self._tbl.setColumnWidth(5, 150)
        self._tbl.setColumnWidth(6, 100)
        lay.addWidget(self._tbl, stretch=1)
        self._df: pd.DataFrame | None = None
        self._load()

    def _load(self):
        mod = self._mod_cb.currentText()
        module = None if mod.startswith("Tous") else mod
        marq   = self._marq_ed.text().strip() or None
        period = self._period_cb.currentText()
        since  = {"Tout": None, "7 derniers jours": 7, "30 derniers jours": 30, "Aujourd'hui": 1}[period]

        rows = queries.get_full_changelog(module=module, marquage=marq, since_days=since)
        self._tbl.setRowCount(0)
        if not rows:
            self._lbl_count.setText("Aucune entrée.")
            self._df = None
            return

        data = [dict(r) for r in rows]
        for r in data:
            ts = r.get("changed_at", "")
            try:
                dt = datetime.fromisoformat(ts)
                r["changed_at"] = dt.strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass

        self._df = pd.DataFrame(data)
        self._lbl_count.setText(f"{len(data)} entrée(s)" + (" — limité à 2000" if len(data) == 2000 else ""))

        for rd in data:
            ri = self._tbl.rowCount()
            self._tbl.insertRow(ri)
            self._tbl.setRowHeight(ri, 26)
            for ci, key in enumerate(["changed_at","marquage","pn_short","field_changed","old_value","new_value","changed_by"]):
                self._tbl.setItem(ri, ci, _ro_item(rd.get(key) or ""))

    def _export_csv(self):
        if self._df is None or self._df.empty:
            QMessageBox.information(self, "Vide", "Aucune donnée à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export historique", f"historique_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "CSV (*.csv)")
        if path:
            self._df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")

    def refresh(self):
        self._load()


# ── Fenêtre principale ────────────────────────────────────────────────────────

class StatsWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistiques — DECA_Master")
        self.resize(1200, 780)
        self.setStyleSheet(f"QDialog {{ background:{_C_BG}; }}")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barre titre + bouton refresh
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 10)
        title = QLabel("📊  Statistiques")
        title.setStyleSheet("font-size:18px; font-weight:bold; color:#1f2937;")
        header.addWidget(title)
        header.addStretch()
        btn_refresh = QPushButton("⟳  Actualiser")
        btn_refresh.setFixedHeight(30)
        btn_refresh.clicked.connect(self._refresh)
        header.addWidget(btn_refresh)
        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(30)
        btn_close.clicked.connect(self.accept)
        header.addWidget(btn_close)

        header_w = QWidget()
        header_w.setStyleSheet(f"background:{_C_CARD_BG}; border-bottom:1px solid #e5e7eb;")
        header_w.setLayout(header)
        lay.addWidget(header_w)

        # Onglets dans un scroll area
        from PyQt6.QtWidgets import QScrollArea
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border:none; }
            QTabBar::tab { padding:8px 18px; font-size:12px; }
            QTabBar::tab:selected { font-weight:bold; color:#1f2937; border-bottom:3px solid #21c354; }
        """)

        def _scrolled(w: QWidget) -> QScrollArea:
            sc = QScrollArea()
            sc.setWidgetResizable(True)
            sc.setWidget(w)
            sc.setStyleSheet("QScrollArea { border:none; }")
            return sc

        self._tab_overview  = _OverviewTab()
        self._tab_activity  = _ActivityTab()
        self._tab_distrib   = _DistribTab()
        self._tab_historique= _HistoriqueTab()

        self._tabs.addTab(_scrolled(self._tab_overview),   "Vue d'ensemble")
        self._tabs.addTab(_scrolled(self._tab_activity),   "Activité")
        self._tabs.addTab(_scrolled(self._tab_distrib),    "Distributions")
        self._tabs.addTab(self._tab_historique,            "Historique")

        lay.addWidget(self._tabs)

    def _refresh(self):
        self._tab_overview.refresh()
        self._tab_activity.refresh()
        self._tab_distrib.refresh()
        self._tab_historique.refresh()
