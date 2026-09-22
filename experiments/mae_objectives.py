"""Quick check: is any other objective better than L1 on MAE? (same split)"""
import warnings, numpy as np, pandas as pd, lightgbm as lgb
from src import config
from src.data_prep import load_clean
from src.features import add_h3
from src.model import build_panel, FEATURES
warnings.filterwarnings("ignore")

df = add_h3(load_clean())
panel, _, all_dates = build_panel(df)
m = panel.dropna(subset=[f"lag_{max(config.LAGS)}"]).copy()
cut = all_dates.max() - pd.Timedelta(days=config.VALID_DAYS)
tr, va = m[m.date <= cut], m[m.date > cut]
yv = va["y"].values
base = float(np.mean(np.abs(va["lag_7"].values - yv)))
print(f"baseline MAE {base:.3f}\n")

def run(obj, label, extra=None):
    p = dict(metric="mae", learning_rate=0.05, num_leaves=63, min_data_in_leaf=50,
             feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1,
             seed=config.RANDOM_STATE, verbose=-1, objective=obj)
    if extra: p.update(extra)
    d = lgb.Dataset(tr[FEATURES], tr["y"])
    dv = lgb.Dataset(va[FEATURES], va["y"], reference=d)
    mdl = lgb.train(p, d, 1500, valid_sets=[dv],
                    callbacks=[lgb.early_stopping(80), lgb.log_evaluation(0)])
    pred = np.clip(mdl.predict(va[FEATURES], num_iteration=mdl.best_iteration), 0, None)
    mae = float(np.mean(np.abs(pred - yv)))
    print(f"  {label:<34} MAE={mae:.3f}  ({100*(base-mae)/base:+.1f}%)")
    return mae

run("regression_l1", "L1 / MAE  [CURRENT]")
run("huber", "Huber")
run("poisson", "Poisson")
for vp in (1.1, 1.3, 1.5):
    run("tweedie", f"Tweedie (variance_power={vp})", {"tweedie_variance_power": vp})
run("regression_l1", "L1 + tuned (leaves 31, lr .03)",
    {"num_leaves": 31, "learning_rate": 0.03, "min_data_in_leaf": 100, "lambda_l2": 2.0})
