-- Source: one row per physical DECA tool, populated by reload_sources.py
CREATE TABLE IF NOT EXISTS tools (
    marquage            TEXT PRIMARY KEY,
    pn_short            TEXT,
    ref_constructeur    TEXT,
    etat                TEXT,
    disponible          TEXT,
    famille             TEXT,
    sous_famille        TEXT,
    type_outil          TEXT,
    application         TEXT,
    commentaire         TEXT,
    procop              TEXT,
    constructeur        TEXT,
    nserie              TEXT,
    service1            TEXT,
    service2            TEXT,
    service3            TEXT,
    service4            TEXT,
    service5            TEXT,
    localisation1       TEXT,
    localisation2       TEXT,
    localisation3       TEXT,
    localisation4       TEXT,
    localisation5       TEXT,

    -- Module enrichment
    modules_panoply     TEXT,   -- comma-separated list from Panoply
    assy_flag           TEXT,   -- normalised ASSY/DISASSY/ASSY AND DISASSY
    modules_esm         TEXT,   -- comma-separated list from DMC/ESM
    modules_effective   TEXT,   -- final merged list used for decisions
    module_source       TEXT,   -- 'panoply_only' | 'esm_only' | 'both' | 'conflict' | 'none'
    module_conflict_detail TEXT, -- if conflict: "Panoply: X | ESM: Y"

    -- ICV operation codes (from DMC, translated via ICV table)
    opcodes_raw         TEXT,   -- comma-separated raw OpCodes from DMC
    opcodes_translated  TEXT,   -- "52AA — Remove Engine Modular Section | ..."

    -- Classification
    is_excluded         INTEGER NOT NULL DEFAULT 0,
    exclusion_reason    TEXT,
    complexity_flag     TEXT,   -- 'unique' | 'multi_deca' | 'multi_module' | 'no_match'
    deca_count          INTEGER,
    eff_mod_count       INTEGER,

    -- Meta
    source_file         TEXT,
    source_format       TEXT,   -- 'may_full' | 'feb_light'
    loaded_at           TEXT
);

-- One row per DECA decision (created/updated by user during precheck/reunion)
CREATE TABLE IF NOT EXISTS decisions (
    marquage        TEXT PRIMARY KEY,
    pn_short        TEXT NOT NULL,
    module_context  TEXT,   -- which module this decision is filed under
    n_service1      TEXT,   -- auto from cascade
    n_service2      TEXT,   -- auto from cascade
    n_service3      TEXT,   -- user selects
    n_service4      TEXT,   -- user selects
    pre_check       TEXT,   -- OK | OK? | NOK | New Service already defined
    decision        TEXT NOT NULL DEFAULT 'EN COURS',
    commentaire     TEXT,
    updated_at      TEXT NOT NULL,
    updated_by      TEXT,
    FOREIGN KEY (marquage) REFERENCES tools(marquage)
);

-- Append-only audit log
CREATE TABLE IF NOT EXISTS changelog (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    marquage        TEXT NOT NULL,
    pn_short        TEXT,
    field_changed   TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    changed_at      TEXT NOT NULL,
    changed_by      TEXT
);

CREATE INDEX IF NOT EXISTS idx_tools_pn      ON tools(pn_short);
CREATE INDEX IF NOT EXISTS idx_tools_excl    ON tools(is_excluded);
CREATE INDEX IF NOT EXISTS idx_tools_complex ON tools(complexity_flag);
CREATE INDEX IF NOT EXISTS idx_dec_pn        ON decisions(pn_short);
CREATE INDEX IF NOT EXISTS idx_dec_status    ON decisions(decision);
CREATE INDEX IF NOT EXISTS idx_dec_module    ON decisions(module_context);
