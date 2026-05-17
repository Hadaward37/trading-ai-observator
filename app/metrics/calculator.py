"""
Metrics Calculator — future expansion point.

Planned: compute financial microstructure metrics from raw trades:
VWAP, rolling volatility, tick imbalance, Kyle's lambda, etc.
"""
from __future__ import annotations
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def compute_vwap(trades: List[Dict[str, Any]]) -> float:
    """Compute volume-weighted average price from a list of trade dicts."""
    if not trades:
        return 0.0
    df = pd.DataFrame(trades)
    df["pv"] = df["price"] * df["quantity"]
    return float(df["pv"].sum() / df["quantity"].sum())
