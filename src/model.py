"""LightGBM model: forecast next-day severity-weighted violation intensity
per hotspot cell. Turns the project from descriptive ("where it's bad now")
into predictive ("where it will be bad tomorrow").
"""
import numpy as np
import pandas as pd
import lightgbm as lgb

from src import config

FEATURES = (
    ["lat", "lon", "junction", "dow", "month", "day", "is_weekend"]
    + [f"lag_{L}" for L in config.LAGS]
    + [f"roll_mean_{W}" for W in config.ROLL_WINDOWS]
    + [f"roll_max_{W}" for W in config.ROLL_WINDOWS]
)


def build_panel(df):
    """Build a (cell x day) panel of weighted-violation intensity with lags."""
    counts = df.groupby("h3")["id"].size()
    keep_cells = counts[counts >= config.MIN_CELL_VIOLATIONS].index
    d = df[df["h3"].isin(keep_cells)].copy()

    daily = (d.groupby(["h3", "date"])
               .agg(y=("severity", "sum"), n=("id", "size"))
               .reset_index())
    daily["date"] = pd.to_datetime(daily["date"])

    # complete the grid so quiet days become explicit zeros
    all_dates = pd.date_range(daily["date"].min(), daily["date"].max(), freq="D")
    idx = pd.MultiIndex.from_product([keep_cells, all_dates], names=["h3", "date"])
    panel = daily.set_index(["h3", "date"]).reindex(idx).reset_index()
    panel["y"] = panel["y"].fillna(0.0)
    panel["n"] = panel["n"].fillna(0.0)

    # cell-static features
    cell_meta = (d.groupby("h3")
                   .agg(lat=("latitude", "mean"),
                        lon=("longitude", "mean"),
                        junction=("has_junction", "mean"))
                   .reset_index())
    panel = panel.merge(cell_meta, on="h3", how="left")

    # calendar features
    panel["dow"] = panel["date"].dt.dayofweek
    panel["month"] = panel["date"].dt.month
    panel["day"] = panel["date"].dt.day
    panel["is_weekend"] = (panel["dow"] >= 5).astype(int)

    # lag & rolling features, strictly per cell and time-ordered
    panel = panel.sort_values(["h3", "date"]).reset_index(drop=True)
    for L in config.LAGS:
        panel[f"lag_{L}"] = panel.groupby("h3")["y"].shift(L)
    panel["_yshift"] = panel.groupby("h3")["y"].shift(1)
    for W in config.ROLL_WINDOWS:
        panel[f"roll_mean_{W}"] = (panel.groupby("h3")["_yshift"]
                                   .rolling(W, min_periods=1).mean()
                                   .reset_index(level=0, drop=True))
        panel[f"roll_max_{W}"] = (panel.groupby("h3")["_yshift"]
                                  .rolling(W, min_periods=1).max()
                                  .reset_index(level=0, drop=True))
    panel = panel.drop(columns="_yshift")
    return panel, keep_cells, all_dates


def train_and_forecast(df):
    panel, keep_cells, all_dates = build_panel(df)
    model_df = panel.dropna(subset=[f"lag_{max(config.LAGS)}"]).copy()

    cutoff = all_dates.max() - pd.Timedelta(days=config.VALID_DAYS)
    train = model_df[model_df["date"] <= cutoff]
    valid = model_df[model_df["date"] > cutoff]

    # objective=regression_l1 (MAE) matches the metric and is far better on the
    # right-skewed daily counts than L2 (which chases rare high-count days).
    params = dict(objective="regression_l1", metric="mae",
                  learning_rate=0.05, num_leaves=63, min_data_in_leaf=50,
                  feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
                  seed=config.RANDOM_STATE, verbose=-1)
    dtrain = lgb.Dataset(train[FEATURES], train["y"])
    dvalid = lgb.Dataset(valid[FEATURES], valid["y"], reference=dtrain)
    model = lgb.train(params, dtrain, num_boost_round=800,
                      valid_sets=[dvalid],
                      callbacks=[lgb.early_stopping(60), lgb.log_evaluation(0)])

    # --- validation metrics vs a naive "same as last week" baseline ---
    pred_v = model.predict(valid[FEATURES], num_iteration=model.best_iteration)
    yv = valid["y"].values
    mae = float(np.mean(np.abs(pred_v - yv)))
    rmse = float(np.sqrt(np.mean((pred_v - yv) ** 2)))
    base_mae = float(np.mean(np.abs(valid["lag_7"].values - yv)))

    # --- next-day forecast: most recent row per cell ---
    last_rows = model_df.sort_values("date").groupby("h3").tail(1).copy()
    fc = model.predict(last_rows[FEATURES], num_iteration=model.best_iteration)
    forecast = last_rows[["h3", "lat", "lon"]].copy()
    forecast["pred_intensity"] = np.clip(fc, 0, None).round(2)
    forecast["forecast_for"] = (all_dates.max() + pd.Timedelta(days=1)).date().isoformat()
    forecast = forecast.sort_values("pred_intensity", ascending=False).reset_index(drop=True)
    forecast["risk_rank"] = forecast.index + 1

    metrics = dict(
        valid_mae=round(mae, 3),
        valid_rmse=round(rmse, 3),
        baseline_lag7_mae=round(base_mae, 3),
        improvement_pct=round(100 * (base_mae - mae) / base_mae, 1) if base_mae else None,
        n_modeled_cells=int(len(keep_cells)),
        best_iteration=int(model.best_iteration),
    )
    return model, forecast, metrics
