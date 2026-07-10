"""All SQL queries for the application — single source of truth."""
from datetime import datetime, timezone
from . import db


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def get_tools_for_module(module: str, include_excluded: bool = False) -> list:
    excl = "" if include_excluded else "AND t.is_excluded = 0"
    return db.fetchall(f"""
        SELECT t.*, d.decision, d.pre_check, d.n_service3, d.n_service4,
               d.commentaire AS dec_commentaire
        FROM tools t
        LEFT JOIN decisions d ON d.marquage = t.marquage
        WHERE t.modules_effective LIKE ? {excl}
        ORDER BY t.pn_short, t.marquage
    """, (f"%{module}%",))


def get_tool(marquage: str) -> db.sqlite3.Row | None:
    return db.fetchone(
        "SELECT * FROM tools WHERE marquage = ?", (marquage,)
    )


def get_excluded_for_pn(pn_short: str) -> list:
    return db.fetchall(
        "SELECT * FROM tools WHERE pn_short = ? AND is_excluded = 1",
        (pn_short,)
    )


def get_pn_list_for_module(module: str) -> list[str]:
    rows = db.fetchall("""
        SELECT DISTINCT t.pn_short
        FROM tools t
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
        ORDER BY t.pn_short
    """, (f"%{module}%",))
    return [r["pn_short"] for r in rows]


def get_pn_stats_for_module(module: str) -> dict:
    """
    Retourne les stats PN pour un module :
    - n_pn_total     : PNs distincts dans ce module
    - n_pn_exclusive : PNs dont AUCUN outil n'apparaît dans un autre module
    - n_pn_done      : PNs dont TOUS les DECAs du module sont VALIDÉ ou EN ATTENTE
    """
    row = db.fetchone("""
        SELECT
            COUNT(DISTINCT t.pn_short) AS n_pn_total,
            COUNT(DISTINCT CASE
                WHEN t.modules_effective NOT LIKE '%,%' THEN t.pn_short END
            ) AS n_pn_exclusive
        FROM tools t
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
    """, (f"%{module}%",))
    base = dict(row) if row else {"n_pn_total": 0, "n_pn_exclusive": 0}

    # PNs "done" : tous leurs DECAs dans ce module ont une décision finale
    done_row = db.fetchone("""
        SELECT COUNT(DISTINCT t.pn_short) AS n_pn_done
        FROM tools t
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
          AND NOT EXISTS (
            SELECT 1 FROM tools t3
            LEFT JOIN decisions d ON d.marquage = t3.marquage
            WHERE t3.pn_short = t.pn_short
              AND t3.modules_effective LIKE ?
              AND t3.is_excluded = 0
              AND (d.decision IS NULL OR d.decision NOT IN ('VALIDÉ','EN ATTENTE'))
          )
    """, (f"%{module}%", f"%{module}%"))
    base["n_pn_done"] = dict(done_row)["n_pn_done"] if done_row else 0
    return base


def get_global_unique_pn_count() -> dict:
    """Compte les PNs uniques globalement (chaque PN une fois, peu importe les modules)."""
    row = db.fetchone("""
        SELECT
            COUNT(DISTINCT pn_short)                                        AS n_pn_global,
            COUNT(DISTINCT CASE WHEN is_excluded = 0 THEN pn_short END)    AS n_pn_active
        FROM tools WHERE pn_short IS NOT NULL
    """)
    return dict(row) if row else {"n_pn_global": 0, "n_pn_active": 0}


def get_deca_count_for_pn(pn_short: str) -> int:
    row = db.fetchone(
        "SELECT COUNT(*) AS cnt FROM tools WHERE pn_short = ? AND is_excluded = 0",
        (pn_short,)
    )
    return row["cnt"] if row else 0


def search_pn(query: str) -> list:
    """
    Returns matching PNs with enough context to navigate directly:
    pn_short, modules_effective, complexity_flag, deca_count, assy_flag.
    One row per PN (aggregated across DECAs).
    """
    q = f"%{query.strip().upper()}%"
    return db.fetchall("""
        SELECT
            pn_short,
            modules_effective,
            module_source,
            module_conflict_detail,
            assy_flag,
            complexity_flag,
            COUNT(*)                                        AS deca_count,
            COUNT(CASE WHEN is_excluded = 0 THEN 1 END)    AS deca_active,
            GROUP_CONCAT(DISTINCT exclusion_reason)         AS exclusion_reasons
        FROM tools
        WHERE UPPER(pn_short) LIKE ?
          AND pn_short IS NOT NULL
        GROUP BY pn_short
        ORDER BY pn_short
        LIMIT 30
    """, (q,))


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

def get_decision(marquage: str) -> db.sqlite3.Row | None:
    return db.fetchone(
        "SELECT * FROM decisions WHERE marquage = ?", (marquage,)
    )


def upsert_decision(
    marquage: str,
    pn_short: str,
    module_context: str,
    n_service1: str | None,
    n_service2: str | None,
    n_service3: str | None,
    n_service4: str | None,
    pre_check: str | None,
    decision: str,
    commentaire: str | None,
    updated_by: str = "system",
) -> None:
    existing = get_decision(marquage)

    # Never overwrite a locked status
    if existing and existing["decision"] in ("VALIDÉ", "EN ATTENTE"):
        return

    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        INSERT INTO decisions
            (marquage, pn_short, module_context,
             n_service1, n_service2, n_service3, n_service4,
             pre_check, decision, commentaire, updated_at, updated_by)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(marquage) DO UPDATE SET
            module_context = excluded.module_context,
            n_service1     = excluded.n_service1,
            n_service2     = excluded.n_service2,
            n_service3     = excluded.n_service3,
            n_service4     = excluded.n_service4,
            pre_check      = excluded.pre_check,
            decision       = excluded.decision,
            commentaire    = excluded.commentaire,
            updated_at     = excluded.updated_at,
            updated_by     = excluded.updated_by
    """, (marquage, pn_short, module_context,
          n_service1, n_service2, n_service3, n_service4,
          pre_check, decision, commentaire, now, updated_by))

    _log_change(marquage, pn_short, "decision", existing["decision"] if existing else None, decision, now, updated_by)


def reset_decision(marquage: str, reset_by: str = "user") -> bool:
    """
    Déverrouille une décision VALIDÉ/EN ATTENTE en la repassant à EN COURS.
    Retourne True si le reset a eu lieu, False si la décision n'existait pas.
    """
    existing = get_decision(marquage)
    if not existing:
        return False
    now = datetime.now(timezone.utc).isoformat()
    db.execute("""
        UPDATE decisions
        SET decision = 'EN COURS', updated_at = ?, updated_by = ?
        WHERE marquage = ?
    """, (now, reset_by, marquage))
    _log_change(marquage, existing["pn_short"], "decision",
                existing["decision"], "EN COURS", now, reset_by)
    return True


def get_decisions_batch_for_module(module: str) -> dict:
    """Retourne {marquage: dict(decision)} en une seule requête — évite N+1."""
    rows = db.fetchall("""
        SELECT d.* FROM decisions d
        JOIN tools t ON t.marquage = d.marquage
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
    """, (f"%{module}%",))
    return {r["marquage"]: dict(r) for r in rows}


def get_all_tools_for_export(module: str) -> list:
    """Tous les DECAs du module (validés, en attente, sans décision) avec infos décision."""
    return db.fetchall("""
        SELECT
            t.marquage, t.pn_short, t.ref_constructeur,
            t.service1, t.service2, t.service3, t.service4, t.service5,
            t.localisation1, t.localisation2, t.localisation3, t.localisation4,
            t.assy_flag, t.complexity_flag, t.modules_effective,
            d.decision, d.n_service1, d.n_service2, d.n_service3, d.n_service4,
            d.pre_check, d.commentaire AS dec_commentaire,
            d.updated_at, d.updated_by
        FROM tools t
        LEFT JOIN decisions d ON d.marquage = t.marquage
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
        ORDER BY t.pn_short, t.marquage
    """, (f"%{module}%",))


def get_decisions_for_export(module: str | None = None) -> list:
    if module:
        return db.fetchall("""
            SELECT d.*, t.ref_constructeur, t.commentaire AS tool_comment
            FROM decisions d
            JOIN tools t ON t.marquage = d.marquage
            WHERE d.decision = 'VALIDÉ' AND d.module_context = ?
            ORDER BY d.pn_short, d.marquage
        """, (module,))
    return db.fetchall("""
        SELECT d.*, t.ref_constructeur, t.commentaire AS tool_comment
        FROM decisions d
        JOIN tools t ON t.marquage = d.marquage
        WHERE d.decision = 'VALIDÉ'
        ORDER BY d.module_context, d.pn_short, d.marquage
    """)


def get_stats_for_module(module: str) -> dict:
    row = db.fetchone("""
        SELECT
            COUNT(CASE WHEN d.decision = 'VALIDÉ'                          THEN 1 END) AS valide,
            COUNT(CASE WHEN d.decision = 'EN ATTENTE'                      THEN 1 END) AS en_attente,
            COUNT(CASE WHEN d.pre_check IS NOT NULL AND d.pre_check != ''
                            AND d.decision NOT IN ('VALIDÉ','EN ATTENTE')  THEN 1 END) AS precheck,
            COUNT(CASE WHEN d.decision = 'EN COURS' OR d.decision IS NULL  THEN 1 END) AS en_cours,
            COUNT(t.marquage)                                                            AS total
        FROM tools t
        LEFT JOIN decisions d ON d.marquage = t.marquage
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
    """, (f"%{module}%",))
    return dict(row) if row else {}


def get_complexity_stats_for_module(module: str) -> dict:
    """Retourne les facteurs bruts pour calculer le score de complexité d'un module."""
    row = db.fetchone("""
        SELECT
            COUNT(t.marquage)                                                              AS n_deca,
            COUNT(DISTINCT t.pn_short)                                                     AS n_pn,
            COUNT(CASE WHEN t.complexity_flag != 'unique' THEN 1 END)                     AS n_complex,
            COUNT(DISTINCT t.service3)                                                     AS n_svc3_distinct,
            COUNT(DISTINCT CASE WHEN t.service4 NOT LIKE '%EXT WH%' THEN t.service4 END) AS n_svc4_internal,
            COUNT(CASE WHEN t.service4 LIKE '%EXT WH%' THEN 1 END)                       AS n_ext_storage
        FROM tools t
        WHERE t.modules_effective LIKE ? AND t.is_excluded = 0
    """, (f"%{module}%",))
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------

def _log_change(marquage, pn_short, field, old_val, new_val, now, by):
    db.execute("""
        INSERT INTO changelog (marquage, pn_short, field_changed, old_value, new_value, changed_at, changed_by)
        VALUES (?,?,?,?,?,?,?)
    """, (marquage, pn_short, field, old_val, new_val, now, by))


def get_changelog(marquage: str) -> list:
    return db.fetchall(
        "SELECT * FROM changelog WHERE marquage = ? ORDER BY changed_at DESC",
        (marquage,)
    )
