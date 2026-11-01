"""Settings shared by the forecasting code.

One fixed random seed, so training a shop's model twice on the same sales gives
the same model (results can be reproduced and compared).
"""

from __future__ import annotations

SEED = 42
