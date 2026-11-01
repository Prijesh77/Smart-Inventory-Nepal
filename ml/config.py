"""Project-wide settings for data preparation and experiments.

Keeping these in one place means every script uses the same store, the same
chronological splits and the same random seed, which makes results reproducible.
"""

from __future__ import annotations

from pathlib import Path

SEED = 42

# Absolute paths, so scripts and the API work from any working folder.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_M5_DIR = PROJECT_ROOT / "data" / "raw" / "m5"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

STORE_ID = "CA_1"
STATE_ID = "CA"  # selects the matching snap_CA column

# Chronological splits by M5 day number (d_1 = 2011-01-29, d_1941 = 2016-05-22).
# Lengths are whole weeks so every split covers each weekday equally.
#   train:      d_1    - d_1395  (~3.8 years)
#   validation: d_1396 - d_1577  (26 weeks) for model selection
#   test:       d_1578 - d_1941  (52 weeks) for final forecasts and inventory simulation
LAST_DAY = 1941
TEST_DAYS = 364
VALIDATION_DAYS = 182
TEST_START = LAST_DAY - TEST_DAYS + 1
VALIDATION_START = TEST_START - VALIDATION_DAYS
TRAIN_END = VALIDATION_START - 1

# Demand classification (Syntetos & Boylan, 2005 cut-off values).
ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49
MIN_TRAIN_DAYS = 365      # need a full year of history to see seasonality
MIN_NONZERO_DAYS = 10     # need enough sales to estimate demand size variability

# Item sample for experiments.
SAMPLE_SIZE = 240
MIN_PER_STRATUM = 8

# Forecast evaluation. Each backtest origin forecasts MAX_HORIZON days ahead;
# metrics are reported for the first 7, 14 and 28 of those days.
FORECAST_HORIZONS = (7, 14, 28)
MAX_HORIZON = max(FORECAST_HORIZONS)
BACKTEST_STEP = 28  # days between origins, so validation windows do not overlap
RESULTS_DIR = PROJECT_ROOT / "experiments" / "results"
MODELS_DIR = PROJECT_ROOT / "models"

# ML training origins inside the training period. A step of 10 days (not a
# multiple of 7) varies the origin weekday, so the model does not only learn
# "the last known day is a Sunday".
TRAIN_ORIGIN_STEP = 10
