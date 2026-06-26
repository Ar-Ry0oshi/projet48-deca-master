from pathlib import Path
import sys

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
DB_PATH = ROOT / "decisions.db"
EXPORTS_DIR = ROOT / "exports"
LOGS_DIR = ROOT / "logs"

# Dossier photos DECA sur le réseau Safran
# UNC path Windows : \\nas01.one.ad\DECA\ssb\Foto Toolings
# Sur Linux (dev) : monter le partage sur /mnt/deca_photos si besoin
_PHOTOS_UNC = r"\\nas01.one.ad\DECA\ssb\Foto Toolings"
if sys.platform == "win32":
    PHOTOS_DIR: Path | None = Path(_PHOTOS_UNC)
else:
    _linux_mount = Path("/mnt/deca_photos")
    PHOTOS_DIR = _linux_mount if _linux_mount.exists() else None

# Expected source filenames (flexible — matched by pattern in reload_sources)
SRC_DECA_PATTERNS = ["*DECA*.csv", "*deca*.csv"]
SRC_PANOPLY_PATTERNS = ["Panoply*.xlsx", "panoply*.xlsx"]
SRC_DMC_PATTERNS = ["DMC*.xlsx", "dmc*.xlsx", "ESM*.xlsx"]
SRC_ICV_PATTERNS = ["ICV*.xlsx", "icv*.xlsx", "*Translation*.xlsx"]

MODULES = [
    "MM01", "MM02", "MM03",
    "SM21", "SM22", "SM24", "SM30", "SM31", "SM32",
    "SM41", "SM51", "SM52", "SM53", "SM54", "SM55",
    "SM56", "SM57", "SM58", "SM59", "SM61", "SM62", "SM63",
]

EXCLUDED_ETATS = {"SOUS ANOMALIE", "PERDU", "REBUT", "HORS GESTION", "EN PRET"}
EXCLUDED_SERVICE_KEYWORDS = {"SCHOOL", "CALIBRATION", "CALIB", "ETALON"}

DECISION_STATUSES = ["EN COURS", "PRÉ-CHECK", "VALIDÉ", "EN ATTENTE"]
PRECHECK_FLAGS = ["OK", "OK?", "NOK", "New Service already defined"]

# Service hierarchy cascade: Service3 → (Service1, Service2)
# Keys must be normalised (uppercase, stripped)
SERVICE_CASCADE: dict[str, tuple[str, str]] = {
    "LSO": ("SAESB", "LSO"),
    **{m: ("SAESB", "MF") for m in MODULES},
}

COMPLEXITY_FLAGS = {
    "unique": "1 PN · 1 DECA · 1 module",
    "multi_deca": "1 PN · N DECAs · 1 module",
    "multi_module": "1 PN · N modules",
    "no_match": "Aucune correspondance module",
}

ROW_COLORS = {
    "OK": "#eaf3de",
    "OK?": "#faeeda",
    "NOK": "#fcebeb",
    "New Service already defined": "#f1efe8",
    None: "transparent",
}
