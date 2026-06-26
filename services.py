"""
Chargement et mise en cache des mappings services depuis SERVICES_EXTRACT.xlsx.

Structure du fichier :
    service1 | service2 | service3 | service4
    (arborescence DECA complète — 24 000 lignes)

Mappings exposés :
    SVC3_OPTIONS          : liste triée des 236 service3
    SVC3_TO_SVC1          : {svc3: [svc1, ...]}  — 1 ou 2 valeurs si ambigu
    SVC3_TO_SVC2          : {svc3: [svc2, ...]}
    SVC1_TO_SVC4          : {svc1: [svc4, ...]}
    SVC1_SVC3_TO_SVC4     : {"svc1||svc3": [svc4, ...]}  — filtrage fin
    SVC1_OPTIONS          : ["SAESB LSO...", "SAESB MF..."]
"""
from functools import lru_cache
from pathlib import Path

import pandas as pd

_SRC = Path(__file__).parent / "ref" / "SERVICES_EXTRACT.xlsx"


@lru_cache(maxsize=1)
def _load() -> dict:
    if not _SRC.exists():
        return _empty()

    df = pd.read_excel(_SRC, dtype=str)
    df = df.fillna("").apply(lambda col: col.str.strip())

    svc3_to_svc1: dict[str, list[str]] = {}
    svc3_to_svc2: dict[str, list[str]] = {}
    for svc3, grp in df.groupby("service3"):
        svc3_to_svc1[svc3] = sorted(grp["service1"].unique().tolist())
        svc3_to_svc2[svc3] = sorted(grp["service2"].unique().tolist())

    svc1_to_svc4: dict[str, list[str]] = {}
    for svc1, grp in df.groupby("service1"):
        svc1_to_svc4[svc1] = sorted(grp["service4"].unique().tolist())

    svc1_svc3_to_svc4: dict[str, list[str]] = {}
    for (svc1, svc3), grp in df.groupby(["service1", "service3"]):
        svc1_svc3_to_svc4[f"{svc1}||{svc3}"] = sorted(grp["service4"].unique().tolist())

    return {
        "svc3_options":       sorted(df["service3"].unique().tolist()),
        "svc3_to_svc1":       svc3_to_svc1,
        "svc3_to_svc2":       svc3_to_svc2,
        "svc1_to_svc4":       svc1_to_svc4,
        "svc1_svc3_to_svc4":  svc1_svc3_to_svc4,
        "svc1_options":       sorted(df["service1"].unique().tolist()),
    }


def _empty() -> dict:
    return {
        "svc3_options": [],
        "svc3_to_svc1": {},
        "svc3_to_svc2": {},
        "svc1_to_svc4": {},
        "svc1_svc3_to_svc4": {},
        "svc1_options": [],
    }


def svc3_options() -> list[str]:
    return _load()["svc3_options"]


def svc1_for_svc3(svc3: str) -> list[str]:
    """Retourne la liste des service1 possibles pour ce service3 (1 ou 2 éléments)."""
    return _load()["svc3_to_svc1"].get(svc3, [])


def svc2_for_svc3(svc3: str) -> list[str]:
    return _load()["svc3_to_svc2"].get(svc3, [])


def svc4_options(svc1: str, svc3: str = "") -> list[str]:
    """
    Retourne les service4 disponibles.
    Si svc3 est fourni, filtre par la combinaison svc1+svc3.
    Sinon retourne tous les svc4 du bâtiment (svc1).
    """
    data = _load()
    if svc3:
        key = f"{svc1}||{svc3}"
        opts = data["svc1_svc3_to_svc4"].get(key)
        if opts:
            return opts
    return data["svc1_to_svc4"].get(svc1, [])


def svc1_options() -> list[str]:
    return _load()["svc1_options"]


def svc1_to_svc4_all() -> dict[str, list[str]]:
    """Retourne le dict complet {svc1: [svc4, ...]}."""
    return _load()["svc1_to_svc4"]
