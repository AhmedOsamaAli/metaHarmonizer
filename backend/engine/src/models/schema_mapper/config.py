"""Configuration constants for schema mapping."""
import os

# === Paths ===
OUTPUT_DIR = "data/schema_mapping_eval"
CURATED_DICT_PATH = "data/schema/curated_fields.csv"
ALIAS_DICT_PATH = ""
VALUE_DICT_PATH = os.getenv("FIELD_VALUE_JSON") or "data/schema/field_value_dict.json"

# === Models ===
FIELD_MODEL = "all-MiniLM-L6-v2"
LLM_MODEL = "gemma-3-27b-it"

# === Thresholds ===
FUZZY_THRESH = 92
NUMERIC_THRESH = 0.6
FIELD_ALIAS_THRESH = 0.5
VALUE_DICT_THRESH = 0.85
VALUE_UNIQUE_CAP = 50
VALUE_PERCENTAGE_THRESH = 0.15
LLM_THRESHOLD = 0.5

# === Noise Values ===
NOISE_VALUES = {
    "yes", "no", "true", "false", "unknown", "not reported", "not available",
    "na", "n/a", "none", "other", "missing", "not evaluated", "uninformative",
    "pending", "undetermined", "positive", "negative", "not applicable"
}