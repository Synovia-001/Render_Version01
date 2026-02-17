from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

def _seasonal_features(dates: pd.Series) -> np.ndarray:
    wk = dates.dt.isocalendar().week.astype(int).to_numpy()
    ang = 2.0 * np.pi * (wk / 52.0)
    return np.column_stack([np.sin(ang), np.cos(ang), wk])

def forecast_next(df_weekly: pd.DataFrame, value_col: str, date_col: str = "Start_Date") -> float | None:
    if df_weekly is None or df_weekly.empty:
        return None
    if date_col not in df_weekly.columns or value_col not in df_weekly.columns:
        return None
    d = df_weekly[[date_col, value_col]].dropna().copy()
    if len(d) < 8:
        return None
    d = d.sort_values(date_col)
    X = _seasonal_features(d[date_col])
    y = d[value_col].astype(float).to_numpy()
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = Ridge(alpha=1.0)
    model.fit(Xs, y)
    next_date = d[date_col].iloc[-1] + pd.Timedelta(days=7)
    Xn = _seasonal_features(pd.Series([next_date]))
    yn = float(model.predict(scaler.transform(Xn))[0])
    return max(0.0, yn)

def anomaly_score_storeprod(df_sp: pd.DataFrame) -> pd.DataFrame:
    if df_sp is None or df_sp.empty:
        return df_sp
    cols = [c for c in ["Units","Value","Base_Units_4W","Base_Value_4W","Units_DevPct_4W","Value_DevPct_4W"] if c in df_sp.columns]
    if not cols:
        return df_sp
    d = df_sp.copy()
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    X = d[cols].to_numpy()
    iso = IsolationForest(n_estimators=200, contamination=0.03, random_state=42)
    iso.fit(X)
    s = -iso.decision_function(X)
    s_norm = (s - s.min()) / (s.max() - s.min()) if s.max() > s.min() else np.zeros_like(s)
    d["ML_AnomalyScore"] = s_norm
    return d
