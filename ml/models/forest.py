"""Random Forest demand model.

A Random Forest averages many decision trees, each trained on a random subset
of rows and features. Averaging makes it far less likely to overfit than a
single tree, and it needs no feature scaling. Its prediction is an average of
past sales in similar situations, so it is never negative.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from ml import config
from ml.features.build import FEATURES

# Chosen for a laptop: max_samples and min_samples_leaf keep training to a few
# minutes and the saved file small. Changing them is a validation experiment,
# never a test-set decision.
RF_PARAMS: dict[str, Any] = {
    "n_estimators": 100,
    "min_samples_leaf": 50,
    "max_features": 0.5,
    "max_samples": 0.3,
    "n_jobs": -1,
    "random_state": config.SEED,
}


def training_rows(rows: pd.DataFrame, last_target_day: int) -> pd.DataFrame:
    """Keep rows usable for fitting: target known, enough history, target inside the fit period."""
    keep = rows["target"].notna() & rows["ma_91"].notna() & (rows["d_num"] <= last_target_day)
    return rows.loc[keep]


def fit_forest(rows: pd.DataFrame, params: dict[str, Any] | None = None) -> RandomForestRegressor:
    model = RandomForestRegressor(**(params or RF_PARAMS))
    model.fit(rows[FEATURES].to_numpy(), rows["target"].to_numpy())
    return model


def predict(model: RandomForestRegressor, rows: pd.DataFrame) -> np.ndarray:
    return model.predict(rows[FEATURES].to_numpy())


def feature_importance(model: RandomForestRegressor) -> pd.Series:
    """Impurity-based importance. Quick but biased towards features with many
    distinct values, so treat it as a rough guide, not proof."""
    return pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)


def save_model(model: RandomForestRegressor, path: Path, metadata: dict[str, Any]) -> None:
    """Save the model plus a JSON file recording how it was made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path, compress=3)
    meta = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": FEATURES,
        "params": {k: v for k, v in model.get_params().items() if k in RF_PARAMS},
        **metadata,
    }
    path.with_suffix(".json").write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
