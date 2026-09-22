"""Offline experiment: can we lower validation MAE without breaking the pipeline?

Tests objective choices and extra features on the SAME time-split as production,
so the comparison is apples-to-apples. Prints a table; ships nothing.
"""
import warnings
import numpy as np
import pandas as pd
import lightgbm as lgb

from src import config
from src.data_prep import load_clean
from src.features import add_h3
from src.model import build_panel, FEATURES as BASE_FEATURES

warnings.filterwarnings("ignore")
np.random.seed(config.RANDOM_STATE)

print("Loading + indexing data ...")
df = add_h3(load_clean())
panel, keep_cells, all_dates = build_panel(df)

# ---- add candidate features on top of the production panel ----
panel = panel.sort_values(["h3", "date"]).reset_index(drop=True)
g = panel.groupby("h3")["y"]
yshift = g.shift(1)
# extra short/seasonal lags
for L in [2, 3, 21]:
    panel[f"lag_{L}"] = g.shift(L)
# rolling std (volatility) + a mid window mean
for W in [7, 14, 28]:
    panel[f"roll_std_{W}"] = (yshift.groupby(panel["h3"]).rolling(W, min_periods=2)
                              .std().reset_index(level=0, drop=True))
panel["roll_mean_14"] = (yshift.groupby(panel["h3"]).rolling(14, min_periods=1)
                         .mean().reset_index(level=0, drop=True))
# EWMA (recency-weighted level)
panel["ewm_7"] = (yshift.groupby(panel["h3"]).ewm(span=7, min_periods=1)
                  .mean().reset_index(level=0, drop=True))
# same-weekday mean over the last 4 occurrences (weekly seasonality, no leak)
sd = panel.groupby(["h3", "dow"])["y"].shift(1)
panel["samedow_mean4"] = (sd.groupby([panel["h3"], panel["dow"]])
                          .rolling(4, min_periods=1).mean()
                          .reset_index(level=[0, 1], drop=True))
# expanding cell mean (shifted -> no leak)
panel["cell_expmean"] = (g.apply(lambda s: s.shift(1).expanding().mean())
                         .reset_index(level=0, drop=True))

panel["roll_std_7"] = panel["roll_std_7"].fillna(0)
panel["roll_std_14"] = panel["roll_std_14"].fillna(0)
panel["roll_std_28"] = panel["roll_std_28"].fillna(0)

EXTRA = ["lag_2", "lag_3", "lag_21", "roll_std_7", "roll_std_14", "roll_std_28",
         "roll_mean_14", "ewm_7", "samedow_mean4", "cell_expmean"]

model_df = panel.dropna(subset=[f"lag_{max(config.LAGS)}"]).copy()
cutoff = all_dates.max() - pd.Timedelta(days=config.VALID_DAYS)
train = model_df[model_df["date"] <= cutoff]
valid = model_df[model_df["date"] > cutoff]
yv = valid["y"].values
base_mae = float(np.mean(np.abs(valid["lag_7"].values - yv)))
print(f"rows train/valid: {len(train):,}/{len(valid):,} | "
      f"same-weekday baseline MAE: {base_mae:.3f}\n")


def run(feats, objective, label, log=False, extra_params=None):
    p = dict(metric="mae", learning_rate=0.05, num_leaves=63, min_data_in_leaf=50,
             feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
             seed=config.RANDOM_STATE, verbose=-1, objective=objective)
    if extra_params:
        p.update(extra_params)
    ytr = np.log1p(train["y"]) if log else train["y"]
    dtr = lgb.Dataset(train[feats], ytr)
    dva = lgb.Dataset(valid[feats], (np.log1p(valid["y"]) if log else valid["y"]),
                      reference=dtr)
    m = lgb.train(p, dtr, num_boost_round=1200, valid_sets=[dva],
                  callbacks=[lgb.early_stopping(80), lgb.log_evaluation(0)])
    pred = m.predict(valid[feats], num_iteration=m.best_iteration)
    if log:
        pred = np.expm1(pred)
    mae = float(np.mean(np.abs(np.clip(pred, 0, None) - yv)))
    imp = 100 * (base_mae - mae) / base_mae
    print(f"  {label:<46} MAE={mae:.3f}  ({imp:+.1f}% vs baseline)  it={m.best_iteration}")
    return mae


print("=== production config (reproduce) ===")
run(BASE_FEATURES, "regression", "L2 objective, base features  [CURRENT]")
print("\n=== change the training objective only (base features) ===")
run(BASE_FEATURES, "regression_l1", "L1/MAE objective")
run(BASE_FEATURES, "huber", "Huber objective")
run(BASE_FEATURES, "fair", "Fair objective")
print("\n=== add features ===")
run(BASE_FEATURES + EXTRA, "regression", "L2 + extra features")
run(BASE_FEATURES + EXTRA, "regression_l1", "L1 + extra features")
run(BASE_FEATURES + EXTRA, "huber", "Huber + extra features")
print("\n=== best combo + mild regularization ===")
run(BASE_FEATURES + EXTRA, "regression_l1", "L1 + extra + L2 reg + smaller leaves",
    extra_params=dict(lambda_l2=1.0, num_leaves=48, min_data_in_leaf=80))
run(BASE_FEATURES + EXTRA, "huber", "Huber + extra + reg",
    extra_params=dict(lambda_l2=1.0, num_leaves=48, min_data_in_leaf=80))
print("\n=== log1p target variants ===")
run(BASE_FEATURES + EXTRA, "regression", "log1p + L2 + extra", log=True)
run(BASE_FEATURES + EXTRA, "regression_l1", "log1p + L1 + extra", log=True)
