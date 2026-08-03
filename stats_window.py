"""Fenêtre Statistiques — PyQt6 + Matplotlib (standalone ou embarquée)."""
from __future__ import annotations

import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.ticker as mticker

from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QPushButton, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame, QSizePolicy, QFileDialog,
    QMessageBox, QScrollArea, QButtonGroup, QRadioButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont

from config import MODULES, DECA_EXTRACTS_DIR, SERVICES_REF_PATH
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

_SVC_COLS = ["service1", "service2", "service3", "service4"]
_LEVELS   = ["S1", "S1-2", "S1-3", "S1-4"]
_BAT_KW   = {"MF": "MF", "LSO": "LSO"}


# ── Petits helpers UI ─────────────────────────────────────────────────────────

def _canvas(fig: Figure) -> FigureCanvasQTAgg:
    c = FigureCanvasQTAgg(fig)
    c.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    c.setMinimumHeight(int(fig.get_figheight() * fig.get_dpi() * 0.9))
    return c


def _card(value: str, label: str, color: str = _C_TEXT) -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.StyledPanel)
    f.setStyleSheet(
        f"QFrame {{ background:{_C_CARD_BG}; border-radius:8px; border:1px solid #e5e7eb; }}"
    )
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
    lbl.setStyleSheet(
        "font-size:13px; font-weight:bold; color:#1f2937; padding-top:8px;"
    )
    return lbl


def _ro_item(text: str, bg: str | None = None) -> QTableWidgetItem:
    it = QTableWidgetItem(str(text) if text is not None else "")
    it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    if bg:
        it.setBackground(QColor(bg))
    return it


def _scrolled(w: QWidget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setWidget(w)
    sc.setStyleSheet("QScrollArea { border:none; }")
    return sc


# ── Onglet 1 — Vue d'ensemble ─────────────────────────────────────────────────

class _OverviewTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(12)
        self._build()

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        stats_rows = queries.get_all_stats_all_modules(MODULES)
        if not stats_rows:
            self._lay.addWidget(QLabel("Aucune donnée en base."))
            self._lay.addStretch()
            return

        df = pd.DataFrame(stats_rows)
        total_g    = int(df["total"].sum())
        valide_g   = int(df["valide"].sum())
        attente_g  = int(df["en_attente"].sum())
        precheck_g = int(df["precheck"].sum())
        encours_g  = int(df["en_cours"].sum())
        traites_g  = valide_g + attente_g
        pct_g      = round(100 * traites_g / total_g) if total_g else 0

        # Count DECAs with complete valid S1→S1-4 from latest extract
        ext_total, ext_s14_n = 0, 0
        ext_label = ""
        try:
            csv_files = _scan_extracts()
            if csv_files and SERVICES_REF_PATH.exists():
                latest = csv_files[0]
                ext_label = latest.stem[:22]
                df_ext = _read_deca_csv(latest.read_bytes())
                ref    = _load_ref()
                kpi    = _compute_kpi(df_ext, ref, "ALL")
                ext_total  = kpi["S1-4"]["total"]
                ext_s14_n  = kpi["S1-4"]["n"]
        except Exception:
            pass
        ext_pct = round(100 * ext_s14_n / ext_total) if ext_total else 0

        row = QHBoxLayout()
        row.addWidget(_card(str(total_g),    "Total DECAs (DB)",  _C_TEXT))
        row.addWidget(_card(str(valide_g),   "Validés (DB)",      _C_VALIDE))
        row.addWidget(_card(str(attente_g),  "En attente",        _C_ATTENTE))
        row.addWidget(_card(str(precheck_g), "Pré-check",         _C_PRECHECK))
        row.addWidget(_card(str(encours_g),  "En cours",          "#9ca3af"))
        row.addWidget(_card(f"{pct_g}%",     "Traités (DB)",      _C_VALIDE if pct_g == 100 else _C_TEXT))
        self._lay.addLayout(row)

        if ext_total:
            ext_row = QHBoxLayout()
            ext_row.addWidget(_card(
                f"{ext_s14_n} / {ext_total}",
                f"S1→S4 complets dans extract\n({ext_label})",
                _C_VALIDE if ext_pct >= 80 else (_C_PRECHECK if ext_pct >= 40 else "#e74c3c"),
            ))
            ext_row.addWidget(_card(
                f"{ext_pct}%",
                "% outils avec service complet (S1-4)",
                _C_VALIDE if ext_pct >= 80 else (_C_PRECHECK if ext_pct >= 40 else "#e74c3c"),
            ))
            ext_row.addStretch()
            self._lay.addLayout(ext_row)

        self._lay.addWidget(_section("Avancement par module"))
        modules   = df["module"].tolist()
        valides   = df["valide"].tolist()
        attentes  = df["en_attente"].tolist()
        prechecks = df["precheck"].tolist()
        encours   = df["en_cours"].tolist()
        totals    = df["total"].tolist()

        fig = Figure(facecolor=_C_BG, figsize=(10, max(3, len(modules) * 0.55 + 1)))
        ax  = fig.add_subplot(111)
        ax.set_facecolor(_C_BG)
        y = range(len(modules))
        h = 0.55
        ax.barh(list(y), valides,   h, color=_C_VALIDE,   label="Validé")
        ax.barh(list(y), attentes,  h, left=valides,      color=_C_ATTENTE,  label="En attente")
        left2 = [v + a for v, a in zip(valides, attentes)]
        ax.barh(list(y), prechecks, h, left=left2,        color=_C_PRECHECK, label="Pré-check")
        left3 = [l + p for l, p in zip(left2, prechecks)]
        ax.barh(list(y), encours,   h, left=left3,        color=_C_ENCOURS,  label="En cours")
        for i, (v, a, t) in enumerate(zip(valides, attentes, totals)):
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

        # Complexité
        self._lay.addWidget(_section("Charge estimée par module"))
        cx_rows = []
        for m in MODULES:
            c = queries.get_complexity_stats_for_module(m)
            if not c or c.get("n_deca", 0) == 0:
                continue
            s = queries.get_stats_for_module(m)
            restant = max(0, c["n_deca"] - s.get("valide", 0) - s.get("en_attente", 0))
            cx_rows.append({
                "module": m, "restant": restant,
                "n_deca": c["n_deca"], "n_pn": c["n_pn"],
                "n_complex": c["n_complex"], "n_svc3": c["n_svc3_distinct"],
                "n_svc4i": c["n_svc4_internal"], "n_ext": c["n_ext_storage"],
            })

        if cx_rows:
            mx = {k: max((x[k] for x in cx_rows), default=1) or 1
                  for k in ("n_deca", "n_pn", "n_complex", "n_svc3", "n_svc4i")}
            scored = sorted(cx_rows, key=lambda r: -(
                (r["n_deca"]   / mx["n_deca"])   * _COMPLEXITY_WEIGHTS["n_deca"] +
                (r["n_pn"]     / mx["n_pn"])      * _COMPLEXITY_WEIGHTS["n_pn"] +
                (r["n_complex"]/ mx["n_complex"]) * _COMPLEXITY_WEIGHTS["n_complex"] +
                (r["n_svc3"]   / mx["n_svc3"])    * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
                (r["n_svc4i"]  / mx["n_svc4i"])   * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
            ))
            headers = ["Module", "Restants", "Score /5", "Cas complexes", "Svc3 ≠", "Svc4 ≠ int.", "Stk ext."]
            tbl = QTableWidget(len(scored), len(headers))
            tbl.setHorizontalHeaderLabels(headers)
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            tbl.setMaximumHeight(min(280, 36 + len(scored) * 30))
            tbl.setAlternatingRowColors(True)
            for ri, r in enumerate(scored):
                sc = (
                    (r["n_deca"]   / mx["n_deca"])   * _COMPLEXITY_WEIGHTS["n_deca"] +
                    (r["n_pn"]     / mx["n_pn"])      * _COMPLEXITY_WEIGHTS["n_pn"] +
                    (r["n_complex"]/ mx["n_complex"]) * _COMPLEXITY_WEIGHTS["n_complex"] +
                    (r["n_svc3"]   / mx["n_svc3"])    * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
                    (r["n_svc4i"]  / mx["n_svc4i"])   * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
                ) * 4 + 1
                stars = "★" * round(sc) + "☆" * (5 - round(sc))
                tbl.setRowHeight(ri, 28)
                for ci, val in enumerate([r["module"], str(r["restant"]),
                    f"{sc:.1f}  {stars}", str(r["n_complex"]),
                    str(r["n_svc3"]), str(r["n_svc4i"]), str(r["n_ext"])]):
                    tbl.setItem(ri, ci, _ro_item(val))
            self._lay.addWidget(tbl)

        self._lay.addStretch()

    def refresh(self):
        self._build()


# ── Onglet 2 — Activité ───────────────────────────────────────────────────────

class _ActivityTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(12)
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

        n_jours    = max((df["day"].iloc[-1] - df["day"].iloc[0]).days, 1)
        vitesse    = df["n"].sum() / n_jours
        cutoff     = df["day"].max() - pd.Timedelta(days=7)
        vitesse_rec= df[df["day"] >= cutoff]["n"].sum() / 7

        all_stats  = [queries.get_stats_for_module(m) for m in MODULES]
        total_deca = sum(s.get("total", 0)      for s in all_stats)
        traites    = sum(s.get("valide", 0) + s.get("en_attente", 0) for s in all_stats)
        restant    = max(0, total_deca - traites)
        if vitesse_rec > 0:
            eta = datetime.now() + timedelta(days=restant / vitesse_rec)
            eta_str = eta.strftime("%d/%m/%Y") + f"  ({int(restant/vitesse_rec)} j)"
        else:
            eta_str = "—"

        kpi_row = QHBoxLayout()
        kpi_row.addWidget(_card(str(int(df["n"].sum())), "Décisions posées"))
        kpi_row.addWidget(_card(f"{vitesse:.1f}/j",      "Vitesse moyenne globale"))
        kpi_row.addWidget(_card(f"{vitesse_rec:.1f}/j",  "Vitesse (7 derniers jours)", _C_VALIDE))
        kpi_row.addWidget(_card(str(restant),             "DECAs restants", "#e74c3c" if restant else _C_VALIDE))
        kpi_row.addWidget(_card(eta_str,                  "Estimation de fin", _C_ATTENTE))
        self._lay.addLayout(kpi_row)

        self._lay.addWidget(_section("Activité journalière et progression cumulée"))
        fig = Figure(facecolor=_C_BG, figsize=(10, 4))
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()
        ax1.set_facecolor(_C_BG)
        ax1.bar(df["day"], df["n"], color=_C_PRECHECK, alpha=0.6, label="Décisions/jour")
        ax2.plot(df["day"], df["cumul"], color=_C_VALIDE, linewidth=2.5, label="Cumulé")
        ax2.fill_between(df["day"], df["cumul"], alpha=0.08, color=_C_VALIDE)
        if vitesse_rec > 0 and restant > 0:
            ax2.axhline(total_deca, color="#e74c3c", linestyle="--", linewidth=1, alpha=0.6)
            ax2.text(df["day"].iloc[-1], total_deca * 1.01, f"  Objectif : {total_deca}",
                     fontsize=8, color="#e74c3c")
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

        self._lay.addWidget(_section("Activité par semaine"))
        df["week"] = df["day"].dt.to_period("W").apply(lambda p: p.start_time)
        df_w = df.groupby("week")["n"].sum().reset_index()
        df_w["lbl"] = df_w["week"].dt.strftime("S%W\n%d/%m")
        fig2 = Figure(facecolor=_C_BG, figsize=(10, 3))
        ax3  = fig2.add_subplot(111)
        ax3.set_facecolor(_C_BG)
        ax3.bar(range(len(df_w)), df_w["n"], color=_C_ATTENTE, alpha=0.85)
        ax3.set_xticks(range(len(df_w)))
        ax3.set_xticklabels(df_w["lbl"], fontsize=8)
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


# ── Onglet 3 — Distributions ──────────────────────────────────────────────────

class _DistribTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(12)
        self._build()

    def _build(self):
        while self._lay.count():
            w = self._lay.takeAt(0).widget()
            if w:
                w.deleteLater()

        all_stats  = [queries.get_stats_for_module(m) for m in MODULES]
        valide_g   = sum(s.get("valide", 0)     for s in all_stats)
        attente_g  = sum(s.get("en_attente", 0) for s in all_stats)
        precheck_g = sum(s.get("precheck", 0)   for s in all_stats)
        encours_g  = sum(s.get("en_cours", 0)   for s in all_stats)

        self._lay.addWidget(_section("Répartition des statuts (global)"))
        half = QHBoxLayout()
        fig_pie = Figure(facecolor=_C_BG, figsize=(4.5, 3.5))
        ax_pie  = fig_pie.add_subplot(111)
        vals    = [valide_g, attente_g, precheck_g, encours_g]
        labels  = ["Validé", "En attente", "Pré-check", "En cours"]
        colors  = [_C_VALIDE, _C_ATTENTE, _C_PRECHECK, _C_ENCOURS]
        nz = [(v, l, c) for v, l, c in zip(vals, labels, colors) if v > 0]
        if nz:
            v2, l2, c2 = zip(*nz)
            _, _, autotexts = ax_pie.pie(v2, labels=l2, colors=c2, autopct="%1.0f%%",
                                          startangle=90, pctdistance=0.78)
            for at in autotexts:
                at.set_fontsize(9)
        fig_pie.tight_layout(pad=1.0)
        half.addWidget(_canvas(fig_pie))

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

        svc4_rows = queries.get_svc4_distribution()
        if svc4_rows:
            self._lay.addWidget(_section("Distribution N.Service 4"))
            df4 = pd.DataFrame([dict(r) for r in svc4_rows]).head(20)
            fig4 = Figure(facecolor=_C_BG, figsize=(10, max(3, len(df4) * 0.42 + 1)))
            ax4  = fig4.add_subplot(111)
            ax4.set_facecolor(_C_BG)
            ax4.barh([str(v)[:40] for v in df4["n_service4"]], df4["n"],
                     color=_C_ATTENTE, alpha=0.85)
            for i, v in enumerate(df4["n"]):
                ax4.text(v + 0.2, i, str(v), va="center", fontsize=8)
            ax4.set_title("Top N.Service 4 assignés", fontsize=10)
            ax4.set_xlabel("Occurrences", fontsize=9)
            ax4.spines["top"].set_visible(False)
            ax4.spines["right"].set_visible(False)
            ax4.invert_yaxis()
            fig4.tight_layout(pad=1.5)
            cv4 = _canvas(fig4)
            cv4.setMinimumHeight(max(200, len(df4) * 25 + 60))
            self._lay.addWidget(cv4)

        pn_rows = []
        for m in MODULES:
            p = queries.get_pn_stats_for_module(m)
            if p.get("n_pn_total", 0):
                excl = p.get("n_pn_exclusive", 0)
                pn_rows.append({"module": m, "exclusifs": excl,
                                 "partagés": p["n_pn_total"] - excl})
        if pn_rows:
            self._lay.addWidget(_section("PNs exclusifs vs partagés par module"))
            df_pn = pd.DataFrame(pn_rows)
            fig5 = Figure(facecolor=_C_BG, figsize=(10, max(3, len(df_pn) * 0.55 + 1)))
            ax5  = fig5.add_subplot(111)
            ax5.set_facecolor(_C_BG)
            y5 = range(len(df_pn))
            ax5.barh(list(y5), df_pn["exclusifs"], 0.5, color=_C_VALIDE,   label="Exclusifs")
            ax5.barh(list(y5), df_pn["partagés"],  0.5, left=df_pn["exclusifs"],
                     color=_C_PRECHECK, label="Partagés")
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


# ── Onglet 4 — Historique ─────────────────────────────────────────────────────

class _HistoriqueTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

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
        btn_export = QPushButton("⬇ Export CSV")
        btn_export.setFixedHeight(28)
        btn_export.clicked.connect(self._export_csv)
        fil.addWidget(btn_export)
        fil.addStretch()
        lay.addLayout(fil)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#6b7280; font-size:11px;")
        lay.addWidget(self._lbl_count)

        self._tbl = QTableWidget()
        self._tbl.setColumnCount(7)
        self._tbl.setHorizontalHeaderLabels(
            ["Date", "Marquage", "PN", "Champ", "Ancienne valeur", "Nouvelle valeur", "Par"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for ci, w in enumerate([145, 100, 90, 70, 150, 150, 100]):
            self._tbl.setColumnWidth(ci, w)
        lay.addWidget(self._tbl, stretch=1)
        self._df: pd.DataFrame | None = None
        self._load()

    def _load(self):
        mod    = self._mod_cb.currentText()
        module = None if mod.startswith("Tous") else mod
        marq   = self._marq_ed.text().strip() or None
        since  = {"Tout": None, "7 derniers jours": 7,
                  "30 derniers jours": 30, "Aujourd'hui": 1}[self._period_cb.currentText()]
        rows   = queries.get_full_changelog(module=module, marquage=marq, since_days=since)
        self._tbl.setRowCount(0)
        if not rows:
            self._lbl_count.setText("Aucune entrée.")
            self._df = None
            return
        data = [dict(r) for r in rows]
        for r in data:
            try:
                r["changed_at"] = datetime.fromisoformat(r["changed_at"]).strftime("%d/%m/%Y %H:%M")
            except Exception:
                pass
        self._df = pd.DataFrame(data)
        self._lbl_count.setText(
            f"{len(data)} entrée(s)" + (" — limité à 2000" if len(data) == 2000 else ""))
        for rd in data:
            ri = self._tbl.rowCount()
            self._tbl.insertRow(ri)
            self._tbl.setRowHeight(ri, 26)
            for ci, key in enumerate(["changed_at","marquage","pn_short",
                                       "field_changed","old_value","new_value","changed_by"]):
                self._tbl.setItem(ri, ci, _ro_item(rd.get(key) or ""))

    def _export_csv(self):
        if self._df is None or self._df.empty:
            QMessageBox.information(self, "Vide", "Aucune donnée à exporter.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export historique",
            f"historique_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "CSV (*.csv)")
        if path:
            self._df.to_csv(path, index=False, sep=";", encoding="utf-8-sig")

    def refresh(self):
        self._load()


# ── Onglet 5 — Progression services ──────────────────────────────────────────

def _scan_extracts() -> list[Path]:
    if not DECA_EXTRACTS_DIR.exists():
        return []
    return sorted(DECA_EXTRACTS_DIR.glob("*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def _read_deca_csv(raw: bytes) -> pd.DataFrame:
    sep = ";" if b";" in raw[:2000] else ","
    df  = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, sep=sep,
                             on_bad_lines="skip", engine="python").fillna("")
            break
        except Exception:
            continue
    if df is None:
        raise ValueError("Encodage non reconnu.")
    df.columns = df.columns.str.strip().str.lower()
    for c in _SVC_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[[c for c in ["marquage"] + _SVC_COLS if c in df.columns]]
    for c in _SVC_COLS:
        df[c] = df[c].str.strip()
    return df


def _load_ref() -> dict[str, set]:
    if not SERVICES_REF_PATH.exists():
        return {}
    df = pd.read_excel(SERVICES_REF_PATH, dtype=str).fillna("")
    df.columns = df.columns.str.strip().str.lower()
    for c in _SVC_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[_SVC_COLS].apply(lambda col: col.str.strip())
    return {
        "S1":   set(zip(df["service1"])),
        "S1-2": set(zip(df["service1"], df["service2"])),
        "S1-3": set(zip(df["service1"], df["service2"], df["service3"])),
        "S1-4": set(zip(df["service1"], df["service2"], df["service3"], df["service4"])),
    }


def _compute_kpi(df: pd.DataFrame, ref: dict, bat: str) -> dict:
    if bat != "ALL":
        kw = _BAT_KW[bat]
        df = df[df["service1"].str.contains(kw, case=False, na=False)]
    total = len(df)
    if total == 0:
        return {lv: {"n": 0, "total": 0, "pct": 0.0} for lv in _LEVELS}
    m1  = df["service1"].ne("") & df["service1"].apply(lambda v: (v,) in ref.get("S1", set()))
    m12 = m1 & df["service2"].ne("") & df.apply(
        lambda r: (r["service1"], r["service2"]) in ref.get("S1-2", set()), axis=1)
    m13 = m12 & df["service3"].ne("") & df.apply(
        lambda r: (r["service1"], r["service2"], r["service3"]) in ref.get("S1-3", set()), axis=1)
    m14 = m13 & df["service4"].ne("") & df.apply(
        lambda r: (r["service1"], r["service2"], r["service3"], r["service4"])
        in ref.get("S1-4", set()), axis=1)
    return {
        "S1":   {"n": int(m1.sum()),  "total": total, "pct": m1.mean()  * 100},
        "S1-2": {"n": int(m12.sum()), "total": total, "pct": m12.mean() * 100},
        "S1-3": {"n": int(m13.sum()), "total": total, "pct": m13.mean() * 100},
        "S1-4": {"n": int(m14.sum()), "total": total, "pct": m14.mean() * 100},
    }


class _ProgressionTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(8)

        # Référentiel
        ref_status = "✅  Référentiel trouvé" if SERVICES_REF_PATH.exists() \
                     else f"❌  Référentiel introuvable : {SERVICES_REF_PATH}"
        lbl_ref = QLabel(ref_status)
        lbl_ref.setStyleSheet("font-size:11px; color:#6b7280;")
        lay.addWidget(lbl_ref)

        # Filtre bâtiment
        bat_row = QHBoxLayout()
        bat_row.addWidget(QLabel("Bâtiment :"))
        self._bat_grp = QButtonGroup(self)
        for i, b in enumerate(["ALL", "MF", "LSO"]):
            rb = QRadioButton(b)
            if i == 0:
                rb.setChecked(True)
            self._bat_grp.addButton(rb, i)
            bat_row.addWidget(rb)
        bat_row.addStretch()
        lay.addLayout(bat_row)

        # Sélecteurs A / B
        sel_row = QHBoxLayout()
        sel_row.addWidget(self._make_selector("A", "ver_a"), stretch=1)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:#ccc;")
        sel_row.addWidget(sep)
        sel_row.addWidget(self._make_selector("B", "ver_b"), stretch=1)
        lay.addLayout(sel_row)

        btn_calc = QPushButton("▶  Calculer la comparaison")
        btn_calc.setFixedHeight(32)
        btn_calc.setStyleSheet(
            "QPushButton { background:#6366f1; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#4f46e5; }"
        )
        btn_calc.clicked.connect(self._compute)
        lay.addWidget(btn_calc)

        self._lbl_err = QLabel("")
        self._lbl_err.setStyleSheet("color:#e74c3c; font-size:11px;")
        lay.addWidget(self._lbl_err)

        # Zone résultat (graphique + table)
        self._result_area = QWidget()
        self._result_lay  = QVBoxLayout(self._result_area)
        self._result_lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._result_area, stretch=1)

        self._df_a: pd.DataFrame | None = None
        self._df_b: pd.DataFrame | None = None

    # ── Sélecteur de version ─────────────────────────────────────────────────

    def _make_selector(self, label: str, key: str) -> QWidget:
        w   = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel(f"<b>Version {label}</b>"))

        csv_files = _scan_extracts()
        cb = QComboBox()
        cb.addItem("— choisir —")
        for f in csv_files:
            cb.addItem(f.name, userData=str(f))
        cb.setMinimumWidth(260)
        lay.addWidget(cb)

        btn_browse = QPushButton("📂  Choisir un fichier…")
        btn_browse.setFixedHeight(26)
        lay.addWidget(btn_browse)

        lbl_info = QLabel("")
        lbl_info.setStyleSheet("font-size:10px; color:#6b7280;")
        lay.addWidget(lbl_info)

        setattr(self, f"_cb_{key}",    cb)
        setattr(self, f"_lbl_{key}",   lbl_info)
        setattr(self, f"_path_{key}",  None)

        def on_select(idx, k=key, c=cb, li=lbl_info):
            path_str = c.currentData()
            if path_str:
                p = Path(path_str)
                mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                li.setText(f"{p.name}  ·  modifié {mtime}")
                setattr(self, f"_path_{k}", path_str)
            else:
                li.setText("")
                setattr(self, f"_path_{k}", None)

        cb.currentIndexChanged.connect(on_select)

        def on_browse(k=key, li=lbl_info, c=cb):
            path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un extrait CSV",
                                                   str(DECA_EXTRACTS_DIR), "CSV (*.csv)")
            if path:
                p = Path(path)
                if c.findText(p.name) < 0:
                    c.addItem(p.name, userData=path)
                c.setCurrentText(p.name)
                setattr(self, f"_path_{k}", path)
                li.setText(p.name)

        btn_browse.clicked.connect(on_browse)
        return w

    # ── Calcul ───────────────────────────────────────────────────────────────

    def _compute(self):
        # Vider résultats
        while self._result_lay.count():
            w = self._result_lay.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._lbl_err.setText("")

        path_a = getattr(self, "_path_ver_a", None)
        path_b = getattr(self, "_path_ver_b", None)
        if not path_a or not path_b:
            self._lbl_err.setText("Sélectionne les deux versions (A et B) avant de calculer.")
            return
        if not SERVICES_REF_PATH.exists():
            self._lbl_err.setText(f"Référentiel introuvable : {SERVICES_REF_PATH}")
            return

        try:
            df_a = _read_deca_csv(Path(path_a).read_bytes())
            df_b = _read_deca_csv(Path(path_b).read_bytes())
            ref  = _load_ref()
        except Exception as e:
            self._lbl_err.setText(f"Erreur de chargement : {e}")
            return

        bat_idx = self._bat_grp.checkedId()
        bat     = ["ALL", "MF", "LSO"][bat_idx]
        kpi_a   = _compute_kpi(df_a.copy(), ref, bat)
        kpi_b   = _compute_kpi(df_b.copy(), ref, bat)

        lbl_a = Path(path_a).stem[:22]
        lbl_b = Path(path_b).stem[:22]

        # ── Graphique entonnoir ────────────────────────────────────────────
        levels = list(reversed(_LEVELS))
        pct_a  = [kpi_a[lv]["pct"] for lv in levels]
        pct_b  = [kpi_b[lv]["pct"] for lv in levels]
        delta  = [b - a for a, b in zip(pct_a, pct_b)]

        fig = Figure(facecolor=_C_BG, figsize=(10, 3.5))
        ax  = fig.add_subplot(111)
        ax.set_facecolor(_C_BG)

        # Barre A (base bleue)
        bars_a = ax.barh(levels, pct_a, 0.45, color="#3b82f6", alpha=0.85, label=lbl_a)
        # Delta B-A (empilé, vert si positif, rouge si négatif)
        d_colors = [_C_VALIDE if d >= 0 else "#e74c3c" for d in delta]
        ax.barh(levels, [abs(d) for d in delta], 0.45,
                left=pct_a, color=d_colors, alpha=0.75)

        # Annotations
        for i, (a, b, d) in enumerate(zip(pct_a, pct_b, delta)):
            ax.text(a / 2, i, f"{a:.1f}%", ha="center", va="center",
                    fontsize=9, color="white", fontweight="bold")
            sign = "+" if d >= 0 else ""
            ax.text(max(a, b) + 1.5, i, f"{sign}{d:.1f}%",
                    va="center", fontsize=9,
                    color=_C_VALIDE if d >= 0 else "#e74c3c")

        ax.set_xlim(0, 110)
        ax.set_xlabel("% outils avec combinaison valide dans le référentiel", fontsize=9)
        ax.set_title(f"Entonnoir services — {lbl_a}  vs  {lbl_b}", fontsize=11)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        from matplotlib.patches import Patch
        legend_els = [
            Patch(color="#3b82f6", label=lbl_a),
            Patch(color=_C_VALIDE, label=f"Δ+ {lbl_b}"),
            Patch(color="#e74c3c", label=f"Δ− {lbl_b}"),
        ]
        ax.legend(handles=legend_els, fontsize=8, loc="lower right")
        fig.tight_layout(pad=1.5)
        self._result_lay.addWidget(_canvas(fig))

        # ── Tableau détail ─────────────────────────────────────────────────
        headers = ["Niveau", f"{lbl_a} (n)", f"{lbl_a} (%)",
                   f"{lbl_b} (n)", f"{lbl_b} (%)", "Δ n", "Δ %"]
        tbl = QTableWidget(len(_LEVELS), len(headers))
        tbl.setHorizontalHeaderLabels(headers)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        tbl.setMaximumHeight(36 + len(_LEVELS) * 30)
        for ri, lv in enumerate(_LEVELS):
            a, b = kpi_a[lv], kpi_b[lv]
            dn = b["n"] - a["n"]
            dp = b["pct"] - a["pct"]
            sign = "+" if dp >= 0 else ""
            row_vals = [lv, str(a["n"]), f"{a['pct']:.1f}%",
                        str(b["n"]), f"{b['pct']:.1f}%",
                        f"{'+' if dn>=0 else ''}{dn}", f"{sign}{dp:.1f}%"]
            tbl.setRowHeight(ri, 28)
            for ci, val in enumerate(row_vals):
                it = _ro_item(val)
                if ci in (5, 6) and dn != 0:
                    it.setForeground(QColor(_C_VALIDE if dn >= 0 else "#e74c3c"))
                tbl.setItem(ri, ci, it)
        self._result_lay.addWidget(tbl)

    def refresh(self):
        pass  # rechargé à la demande via le bouton Calculer


# ── Fenêtre principale ────────────────────────────────────────────────────────

class StatsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Statistiques — DECA_Master")
        self.resize(1250, 820)
        self.setStyleSheet(f"QMainWindow {{ background:{_C_BG}; }}")

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 10)
        title = QLabel("📊  Statistiques DECA_Master")
        title.setStyleSheet("font-size:17px; font-weight:bold; color:#1f2937;")
        header.addWidget(title)
        header.addStretch()
        btn_refresh = QPushButton("⟳  Actualiser")
        btn_refresh.setFixedHeight(30)
        btn_refresh.clicked.connect(self._refresh)
        header.addWidget(btn_refresh)
        header_w = QWidget()
        header_w.setStyleSheet(f"background:{_C_CARD_BG}; border-bottom:1px solid #e5e7eb;")
        header_w.setLayout(header)
        lay.addWidget(header_w)

        # Onglets
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet("""
            QTabWidget::pane { border:none; }
            QTabBar::tab { padding:8px 18px; font-size:12px; }
            QTabBar::tab:selected { font-weight:bold; border-bottom:3px solid #21c354; }
        """)

        self._tab_overview   = _OverviewTab()
        self._tab_activity   = _ActivityTab()
        self._tab_distrib    = _DistribTab()
        self._tab_historique = _HistoriqueTab()
        self._tab_progression= _ProgressionTab()

        self._tabs.addTab(_scrolled(self._tab_overview),   "Vue d'ensemble")
        self._tabs.addTab(_scrolled(self._tab_activity),   "Activité")
        self._tabs.addTab(_scrolled(self._tab_distrib),    "Distributions")
        self._tabs.addTab(self._tab_historique,            "Historique")
        self._tabs.addTab(_scrolled(self._tab_progression),"Progression services")

        lay.addWidget(self._tabs)

    def _refresh(self):
        self._tab_overview.refresh()
        self._tab_activity.refresh()
        self._tab_distrib.refresh()
        self._tab_historique.refresh()
