"""Demand pattern of each product, from its own sales history.

The Syntetos-Boylan classification sorts items by two numbers:

  ADI  average demand interval: available days / days with a sale (1 = sells every day)
  CV2  squared coefficient of variation of the sale sizes on the days it sells

  smooth        ADI < 1.32 and CV2 < 0.49   sells most days, in similar amounts
  erratic       ADI < 1.32 and CV2 >= 0.49  sells most days, amounts jump around
  intermittent  ADI >= 1.32 and CV2 < 0.49  many zero days, similar amounts when it sells
  lumpy         ADI >= 1.32 and CV2 >= 0.49 many zero days and very uneven amounts

The cut-offs are the ones published with the classification (Syntetos, Boylan & Croston, 2005).
Different forecasting methods suit different patterns, so the app scores and chooses its model
per pattern.
"""

from __future__ import annotations

import numpy as np

ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49
MIN_SALE_DAYS = 2          # fewer days with a sale than this: too little to tell
UNKNOWN = "unknown"
PATTERNS = ("smooth", "erratic", "intermittent", "lumpy")


def classify_demand(sales: np.ndarray) -> np.ndarray:
    """One pattern name per row of an items x days matrix. NaN days (not on sale, store closed) are ignored."""
    sales = np.atleast_2d(np.asarray(sales, dtype=float))
    out = np.full(sales.shape[0], UNKNOWN, dtype=object)
    for i, row in enumerate(sales):
        available = row[~np.isnan(row)]
        sold = available[available > 0]
        if sold.size < MIN_SALE_DAYS:
            continue
        adi = available.size / sold.size
        cv2 = (sold.std() / sold.mean()) ** 2
        intermittent, uneven = adi >= ADI_CUTOFF, cv2 >= CV2_CUTOFF
        out[i] = ("lumpy" if uneven else "intermittent") if intermittent else ("erratic" if uneven else "smooth")
    return out
