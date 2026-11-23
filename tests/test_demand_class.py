import numpy as np

from ml.features.demand_class import classify_demand


def test_the_four_patterns_and_unknown():
    days = 60
    smooth = np.full(days, 5.0)                                   # every day, same amount
    erratic = np.tile([1.0, 12.0], days // 2)                     # every day, very different amounts
    intermittent = np.tile([0.0, 0.0, 3.0], days // 3)            # one day in three, same amount
    lumpy = np.tile([0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 20.0], 8)[:days]   # rare and very uneven
    unknown = np.zeros(days)
    unknown[10] = 4.0                                             # a single sale is too little to tell
    result = classify_demand(np.vstack([smooth, erratic, intermittent, lumpy, unknown]))
    assert list(result) == ["smooth", "erratic", "intermittent", "lumpy", "unknown"]


def test_days_not_on_sale_are_ignored():
    row = np.array([np.nan] * 30 + [4.0] * 30)                    # only on sale for the last 30 days, sold every day
    assert classify_demand(row)[0] == "smooth"
