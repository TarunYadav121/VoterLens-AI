"""
config.py — VoterLens AI
========================
Single source of truth for all configurable constants, thresholds,
column definitions, and rule parameters.

No magic numbers should appear in any other module.
Import from this module instead.
"""

# ---------------------------------------------------------------------------
# Application metadata
# ---------------------------------------------------------------------------

APP_NAME = "VoterLens AI"
APP_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# File upload limits
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024   # 20 MB
MAX_ROW_COUNT = 100_000                  # rows per CSV (enforced after header)
ALLOWED_EXTENSIONS = {".csv"}

# ---------------------------------------------------------------------------
# In-memory analysis store
# ---------------------------------------------------------------------------

MAX_STORED_ANALYSES = 10   # LRU eviction when exceeded

# ---------------------------------------------------------------------------
# CSV schema — required columns
# Every required column absent → ERROR (analysis blocked)
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS = [
    "record_id",
    "name",
    "area_id",
    "area_name",
]

# ---------------------------------------------------------------------------
# CSV schema — optional columns
# Absent optional column → WARNING (analysis continues with reduced features)
# ---------------------------------------------------------------------------

OPTIONAL_COLUMNS = [
    "age",
    "gender",
    "area_type",
    "population_group",
    "administrative_category",
    "polling_station_id",
    "registration_date",
]

# All columns in schema order (used for generator and validation)
ALL_SCHEMA_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

# ---------------------------------------------------------------------------
# Fields compared between previous and current versions of the same record_id
# Changing any of these fields → MODIFIED classification
# ---------------------------------------------------------------------------

COMPARISON_FIELDS = [
    "name",
    "age",
    "gender",
    "area_id",
    "area_name",
    "area_type",
    "population_group",
    "administrative_category",
    "polling_station_id",
    "registration_date",
]

# ---------------------------------------------------------------------------
# Allowed values for categorical fields
# ---------------------------------------------------------------------------

ALLOWED_GENDER = {"M", "F", "O", "U", ""}        # O = other, U = unknown
ALLOWED_AREA_TYPE = {"urban", "rural", "semi-urban", ""}

# ---------------------------------------------------------------------------
# Age plausibility range (configurable — not a legal requirement)
# ---------------------------------------------------------------------------

AGE_MIN_PLAUSIBLE = 17
AGE_MAX_PLAUSIBLE = 120

# ---------------------------------------------------------------------------
# Pagination defaults
# ---------------------------------------------------------------------------

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 1000

# ---------------------------------------------------------------------------
# Detection thresholds
# Rates are expressed as fractions (0.0–1.0)
# ---------------------------------------------------------------------------

# Area-level aggregate thresholds
THRESHOLD_REMOVAL_RATE = 0.20      # Flag if removal rate > this + baseline
THRESHOLD_ADDITION_RATE = 0.20     # Flag if addition rate > this + baseline

# Minimum comparison-group size for similar-area baseline calculation
MIN_COMPARISON_GROUP_SIZE = 3

# ---------------------------------------------------------------------------
# Detection rules registry
# Each rule has a unique ID, human-readable name, default severity,
# and optional threshold value.
# ---------------------------------------------------------------------------

DETECTION_RULES = {
    "RULE-D-001": {
        "name": "DUPLICATE_ID",
        "description": "One or more record_id values appear more than once in the same file.",
        "severity": "ERROR",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-002": {
        "name": "MISSING_REQUIRED_VALUE",
        "description": "A required field (name, area_id, or area_name) is null or empty.",
        "severity": "WARNING",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-003": {
        "name": "MISSING_AGE",
        "description": "The age field is null or empty for one or more records.",
        "severity": "WARNING",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-004": {
        "name": "INVALID_AGE",
        "description": "The age field contains a non-numeric value that cannot be interpreted as an integer.",
        "severity": "ERROR",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-005": {
        "name": "OUT_OF_RANGE_AGE",
        "description": f"Age is outside the configured plausible range [{AGE_MIN_PLAUSIBLE}, {AGE_MAX_PLAUSIBLE}].",
        "severity": "REVIEW_FLAG",
        "threshold": (AGE_MIN_PLAUSIBLE, AGE_MAX_PLAUSIBLE),
        "category": "DATA_QUALITY",
    },
    "RULE-D-006": {
        "name": "INVALID_GENDER",
        "description": "Gender value is not in the allowed set (M, F, O, U).",
        "severity": "REVIEW_FLAG",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-007": {
        "name": "HIGH_REMOVAL_RATE",
        "description": "Area removal rate substantially exceeds the comparison baseline.",
        "severity": "REVIEW_FLAG",
        "threshold": THRESHOLD_REMOVAL_RATE,
        "category": "AGGREGATE_PATTERN",
    },
    "RULE-D-008": {
        "name": "HIGH_ADDITION_RATE",
        "description": "Area addition rate substantially exceeds the comparison baseline.",
        "severity": "REVIEW_FLAG",
        "threshold": THRESHOLD_ADDITION_RATE,
        "category": "AGGREGATE_PATTERN",
    },
    "RULE-D-009": {
        "name": "INVALID_DATE_FORMAT",
        "description": "registration_date is present but does not match ISO 8601 (YYYY-MM-DD).",
        "severity": "REVIEW_FLAG",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
    "RULE-D-010": {
        "name": "INVALID_AREA_TYPE",
        "description": "area_type value is not in the allowed set (urban, rural, semi-urban).",
        "severity": "REVIEW_FLAG",
        "threshold": None,
        "category": "DATA_QUALITY",
    },
}

# ---------------------------------------------------------------------------
# Validation rule IDs (for cross-reference in validator.py)
# ---------------------------------------------------------------------------

VALIDATION_RULES = {
    "RULE-V-001": "record_id is null or empty string",
    "RULE-V-002": "record_id appears more than once in the same file",
    "RULE-V-003": "Missing required column",
    "RULE-V-004": "File is empty (zero data rows after header)",
    "RULE-V-005": "File cannot be parsed as CSV",
    "RULE-V-006": "File exceeds maximum allowed size",
    "RULE-V-007": "Row count exceeds maximum allowed rows",
    "RULE-V-008": "Unsupported file type (must be .csv)",
    "RULE-V-009": "age is null or empty (missing value)",
    "RULE-V-010": "age is not numeric",
    "RULE-V-011": "age is outside configurable plausible range",
    "RULE-V-012": "gender is not in allowed values",
    "RULE-V-013": "area_type is not in allowed values",
    "RULE-V-014": "registration_date is not ISO 8601 (YYYY-MM-DD)",
    "RULE-V-015": "name is null or empty",
    "RULE-V-016": "area_id is null or empty",
}

# ---------------------------------------------------------------------------
# Multilingual explanation templates (used by explainer.py)
# ---------------------------------------------------------------------------

EXPLANATION_TEMPLATES = {
    "HIGH_REMOVAL_RATE": {
        "technical": (
            "Area {area_id} ({area_name}) exhibits a removal rate of {rate:.1f}%, "
            "which is {diff:.1f} percentage points above the {method} baseline of "
            "{baseline:.1f}% (group size: {n}). This exceeds the configured threshold "
            "of {threshold_pp:.1f} pp above the baseline. Rule: RULE-D-007."
        ),
        "simple": (
            "In area {area_name}, a large number of voters have been removed compared "
            "with other areas. {deleted_count} out of {previous_count} previous records "
            "are no longer in the current list ({rate:.1f}%). This is higher than the "
            "average for other areas ({baseline:.1f}%) and has been flagged for review."
        ),
        "hindi": (
            "क्षेत्र {area_name} में पिछली सूची के {previous_count} रिकॉर्ड में से "
            "{deleted_count} रिकॉर्ड हटाए गए हैं ({rate:.1f}%)। "
            "यह दर अन्य क्षेत्रों की औसत दर ({baseline:.1f}%) से अधिक है "
            "और मानव समीक्षा के लिए चिह्नित किया गया है।"
        ),
    },
    "HIGH_ADDITION_RATE": {
        "technical": (
            "Area {area_id} ({area_name}) exhibits an addition rate of {rate:.1f}%, "
            "which is {diff:.1f} percentage points above the {method} baseline of "
            "{baseline:.1f}% (group size: {n}). Rule: RULE-D-008."
        ),
        "simple": (
            "In area {area_name}, a large number of new voters have been added compared "
            "with other areas. {added_count} new records represent {rate:.1f}% of the "
            "current list. This is higher than usual ({baseline:.1f}%) and has been "
            "flagged for review."
        ),
        "hindi": (
            "क्षेत्र {area_name} में {added_count} नए रिकॉर्ड जोड़े गए हैं ({rate:.1f}%)। "
            "यह दर अन्य क्षेत्रों की औसत ({baseline:.1f}%) से अधिक है "
            "और समीक्षा के लिए चिह्नित है।"
        ),
    },
    "DISCLAIMER": {
        "technical": (
            "This finding is a statistical signal generated by a deterministic rule. "
            "It does not constitute evidence of wrongdoing and must not be presented "
            "as such. Independent verification of the underlying records and source "
            "data is required before drawing any conclusion."
        ),
        "simple": (
            "This flag does not prove wrongdoing. It means the "
            "numbers look unusual compared with other areas, and a reviewer should "
            "check the original source documents."
        ),
        "hindi": (
            "यह चिह्न किसी गलत काम का प्रमाण नहीं है। इसका अर्थ है कि संख्याएँ "
            "असामान्य दिखती हैं और एक समीक्षक को मूल स्रोत दस्तावेजों की जाँच करनी चाहिए।"
        ),
    },
}

# ---------------------------------------------------------------------------
# Data generator settings
# ---------------------------------------------------------------------------

GENERATOR_RANDOM_SEED = 42

GENERATOR_AREA_IDS = ["A01", "B01", "C01", "D01", "E01"]
GENERATOR_AREA_NAMES = {
    "A01": "North Valley",
    "B01": "South Bend",
    "C01": "East Ridge",
    "D01": "West Creek",
    "E01": "Central Plains",
}
GENERATOR_AREA_TYPES = {
    "A01": "urban",
    "B01": "urban",
    "C01": "rural",
    "D01": "semi-urban",
    "E01": "rural",
}
GENERATOR_POPULATION_GROUPS = {
    "A01": "group-1",
    "B01": "group-2",
    "C01": "group-3",
    "D01": "group-2",
    "E01": "group-3",
}

# ---------------------------------------------------------------------------
# AI Insight Assistant configuration
# ---------------------------------------------------------------------------

DEFAULT_AI_PROVIDER = "gemini"
DEFAULT_AI_MODEL = "gemini-2.0-flash"
DEFAULT_AI_MAX_TOKENS = 1024
DEFAULT_AI_TIMEOUT_SECONDS = 30
MAX_QUESTION_LENGTH = 500
SUPPORTED_LANGUAGES = {"en", "hi"}
