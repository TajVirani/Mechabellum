from __future__ import annotations

from typing import Any, Literal

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPSILON = 1e-6


class CalibratedModel:
    """A trained classifier followed by a probability map fitted on held-out matches.

    `sigmoid` fits Platt scaling on the base model's log-odds; `isotonic` fits a monotone step function. The base
    model is never refit, so the calibration slice only shapes the probabilities.
    """

    def __init__(self, base: Any, method: Literal["sigmoid", "isotonic"]) -> None:
        self.base = base
        self.method = method
        self._map: Any = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> CalibratedModel:
        scores = self._base_scores(x)
        if self.method == "sigmoid":
            self._map = LogisticRegression(C=1e6).fit(scores.reshape(-1, 1), y)
        else:
            self._map = IsotonicRegression(y_min=EPSILON, y_max=1 - EPSILON, out_of_bounds="clip").fit(
                self._base_probabilities(x), y
            )
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self._map is None:
            raise ValueError("The calibration map has not been fitted.")
        if self.method == "sigmoid":
            positive = self._map.predict_proba(self._base_scores(x).reshape(-1, 1))[:, 1]
        else:
            positive = self._map.predict(self._base_probabilities(x))
        positive = np.clip(positive, EPSILON, 1 - EPSILON)
        return np.column_stack([1 - positive, positive])

    def _base_probabilities(self, x: np.ndarray) -> np.ndarray:
        return self.base.predict_proba(x)[:, 1]

    def _base_scores(self, x: np.ndarray) -> np.ndarray:
        probabilities = np.clip(self._base_probabilities(x), EPSILON, 1 - EPSILON)
        return np.log(probabilities / (1 - probabilities))
