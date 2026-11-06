"""
Home-grown expected-goals (xG) model.

WhoScored/Opta match-event data carries no xG, so this fits one on the shots
we already have: a regularised logistic regression on shot geometry plus the
qualifier flags Opta already records (head, big chance, set-piece type, fast
break, assisted). Labels are the real outcomes (goal / no goal) of every
non-penalty shot in the dataset, so the model is calibrated to *this* data
by construction -- the build script prints total xG vs total goals as a
sanity check.

The fitted coefficients are saved to data/advanced/xg_model.json (a few
hundred bytes). The running web app only ever loads that file; numpy-only,
no scikit-learn dependency, nothing is refit at request time.

Penalties are not modelled -- they get a flat conversion rate (also fitted).
"""

import json
import math
import os

import numpy as np

from core.advanced import config

MODEL_PATH = os.path.join(config.ADVANCED_DATA_DIR, "xg_model.json")

# Real pitch size used to turn the 0-100 Opta grid into metres for geometry.
_LEN_M, _WID_M = 105.0, 68.0
_HALF_GOAL_M = 7.32 / 2

FEATURES = [
    "dist_m", "dist_m_sq", "angle_rad", "is_head", "is_big_chance",
    "is_direct_fk", "is_corner", "is_other_set_piece", "is_fast_break",
    "is_assisted", "is_other_body_part",
]


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    """(distance in metres to goal centre, angle in radians subtended by the posts)."""
    dx = (100.0 - x) / 100.0 * _LEN_M
    dy = (50.0 - y) / 100.0 * _WID_M
    dx = max(dx, 0.01)  # shots recorded on/behind the line: avoid divide-by-zero
    dist = math.hypot(dx, dy)
    # Angle between the two lines from the shot to each post.
    a1 = math.atan2(_HALF_GOAL_M - dy, dx)
    a2 = math.atan2(-_HALF_GOAL_M - dy, dx)
    return dist, abs(a1 - a2)


def feature_vector(x: float, y: float, flags: dict) -> list[float]:
    dist, angle = shot_geometry(x, y)
    return [
        dist, dist * dist, angle,
        float(flags.get("head", False)),
        float(flags.get("big_chance", False)),
        float(flags.get("direct_fk", False)),
        float(flags.get("corner", False)),
        float(flags.get("other_set_piece", False)),
        float(flags.get("fast_break", False)),
        float(flags.get("assisted", False)),
        float(flags.get("other_body_part", False)),
    ]


def fit(X: np.ndarray, y: np.ndarray, penalty_rate: float, l2: float = 1e-2, iters: int = 40) -> dict:
    """Newton-Raphson (IRLS) logistic regression on standardised features."""
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    reg = np.eye(Z.shape[1]) * l2
    reg[0, 0] = 0.0  # don't penalise the intercept
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ w, -30, 30)))
        grad = Z.T @ (p - y) + reg @ w
        s = p * (1 - p)
        hess = (Z * s[:, None]).T @ Z + reg
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return {
        "features": FEATURES,
        "mean": mu.tolist(),
        "std": sd.tolist(),
        "intercept": float(w[0]),
        "coef": w[1:].tolist(),
        "penalty_xg": float(penalty_rate),
    }


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    Z = (X - np.array(model["mean"])) / np.array(model["std"])
    logit = model["intercept"] + Z @ np.array(model["coef"])
    return 1.0 / (1.0 + np.exp(-np.clip(logit, -30, 30)))


def save(model: dict, path: str = MODEL_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(model, f, indent=1)


def load(path: str = MODEL_PATH) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)
