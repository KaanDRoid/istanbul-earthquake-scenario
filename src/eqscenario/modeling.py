"""Cross-validated models of scenario casualties from building damage."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import LinearRegression, PoissonRegressor
from sklearn.metrics import mean_absolute_error, mean_poisson_deviance, r2_score
from sklearn.model_selection import GroupKFold, KFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from .data import DAMAGE_COLS, DAMAGE_LABELS

TARGET = "deaths_serious"
N_SPLITS = 5
SEED = 42
PRED_FLOOR = 1e-3  # Poisson deviance needs positive predictions


def make_models() -> dict:
    return {
        "Ratio baseline (very heavy only)": (
            LinearRegression(fit_intercept=False),
            [DAMAGE_COLS[0]],
        ),
        "Linear regression": (LinearRegression(), DAMAGE_COLS),
        "Poisson GLM (log1p features)": (
            make_pipeline(
                FunctionTransformer(np.log1p),
                StandardScaler(),
                PoissonRegressor(alpha=1e-4, max_iter=2000),
            ),
            DAMAGE_COLS,
        ),
        "Gradient boosting (Poisson loss)": (
            HistGradientBoostingRegressor(
                loss="poisson",
                learning_rate=0.05,
                max_iter=300,
                min_samples_leaf=20,
                random_state=SEED,
            ),
            DAMAGE_COLS,
        ),
    }


def splitters(groups: pd.Series) -> dict:
    return {
        "random 5-fold": (KFold(N_SPLITS, shuffle=True, random_state=SEED), None),
        "grouped by district 5-fold": (GroupKFold(N_SPLITS), groups.to_numpy()),
    }


def _scores(y, pred) -> dict:
    return {
        "r2": r2_score(y, pred),
        "mae": mean_absolute_error(y, pred),
        "poisson_dev": mean_poisson_deviance(y, np.clip(pred, PRED_FLOOR, None)),
    }


def cross_validate(df: pd.DataFrame, target: str = TARGET):
    """Return per-fold scores and out-of-fold predictions for every model/split."""
    y = df[target].to_numpy(dtype=float)
    fold_rows, oof = [], {}
    for split_name, (cv, groups) in splitters(df["district"]).items():
        folds = list(cv.split(df, y, groups))
        for model_name, (model, cols) in make_models().items():
            X = df[cols].to_numpy(dtype=float)
            pred = np.zeros_like(y)
            for k, (tr, te) in enumerate(folds):
                m = clone(model).fit(X[tr], y[tr])
                pred[te] = m.predict(X[te])
                fold_rows.append(
                    {
                        "split": split_name,
                        "model": model_name,
                        "fold": k,
                        **_scores(y[te], pred[te]),
                    }
                )
            oof[(split_name, model_name)] = pred
    folds_df = pd.DataFrame(fold_rows)
    summary = folds_df.groupby(["split", "model"], sort=False)[
        ["r2", "mae", "poisson_dev"]
    ].agg(["mean", "std"])
    summary.columns = [f"{a}_{b}" for a, b in summary.columns]
    return folds_df, summary.reset_index(), oof


def per_building_rates(df: pd.DataFrame, target: str = TARGET) -> pd.DataFrame:
    """Casualties per building at each damage level.

    Linear fit without intercept and with non-negative coefficients, so each
    coefficient reads as 'casualties per building in this damage level'.
    """
    X = df[DAMAGE_COLS].to_numpy(dtype=float)
    y = df[target].to_numpy(dtype=float)
    lr = LinearRegression(fit_intercept=False, positive=True).fit(X, y)
    share = (X * lr.coef_).sum(axis=0) / (X @ lr.coef_).sum()
    return pd.DataFrame(
        {
            "damage_level": [DAMAGE_LABELS[c] for c in DAMAGE_COLS],
            "buildings_total": X.sum(axis=0).astype(int),
            "casualties_per_building": lr.coef_,
            "share_of_fitted_casualties": share,
        }
    )


def single_feature_cv(df: pd.DataFrame, target: str = TARGET) -> pd.DataFrame:
    """Grouped-CV scores of a Poisson GLM seeing one damage level at a time."""
    y = df[target].to_numpy(dtype=float)
    cv, groups = splitters(df["district"])["grouped by district 5-fold"]
    rows = []
    for col in DAMAGE_COLS:
        X = df[[col]].to_numpy(dtype=float)
        model = make_pipeline(
            FunctionTransformer(np.log1p),
            StandardScaler(),
            PoissonRegressor(alpha=1e-4, max_iter=2000),
        )
        pred = np.zeros_like(y)
        fold_r2 = []
        for tr, te in cv.split(X, y, groups):
            pred[te] = clone(model).fit(X[tr], y[tr]).predict(X[te])
            fold_r2.append(r2_score(y[te], pred[te]))
        rows.append(
            {
                "damage_level": DAMAGE_LABELS[col],
                "grouped_cv_r2_mean": np.mean(fold_r2),
                "grouped_cv_r2_std": np.std(fold_r2, ddof=1),
                "pooled_oof_r2": r2_score(y, pred),
                "spearman_with_target": df[col].corr(df[target], method="spearman"),
            }
        )
    return pd.DataFrame(rows)
