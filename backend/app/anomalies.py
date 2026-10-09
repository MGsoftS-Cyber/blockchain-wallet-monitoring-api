"""Per-asset fixed earlier baseline; scores are not fraud probabilities."""

import math
from collections import defaultdict
import numpy as np
from sklearn.ensemble import IsolationForest
from threadpoolctl import threadpool_limits

PARAMETERS = dict(
    training_events=30,
    min_scoring_events=10,
    n_estimators=100,
    contamination=0.1,
    random_state=42,
    features=["log1p(base-unit amount)", "log1p(seconds since previous same-asset event)", "outgoing flag"],
)


def detect(transfers, enabled):
    if not enabled:
        return dict(status="disabled", parameters=PARAMETERS, assets=[], scores=[])
    grouped = defaultdict(list)
    for t in transfers:
        if t["direction"] != "self" and int(t["amount_base_units"]) > 0:
            grouped[t["asset_id"]].append(t)
    assets = []
    scores = []
    for asset, rows in sorted(grouped.items()):
        if len(rows) < 40:
            assets.append(dict(asset_id=asset, status="insufficient_history", event_count=len(rows)))
            continue
        previous = rows[0]["timestamp"]
        features = []
        for t in rows:
            features.append(
                [
                    math.log1p(int(t["amount_base_units"])),
                    math.log1p(t["timestamp"] - previous),
                    float(t["direction"] == "out"),
                ]
            )
            previous = t["timestamp"]
        x = np.array(features, dtype="float64")
        with threadpool_limits(limits=1):
            model = IsolationForest(n_estimators=100, contamination=0.1, random_state=42, n_jobs=1).fit(x[:30])
            values = model.score_samples(x[30:])
        assets.append(
            dict(
                asset_id=asset,
                status="available",
                training_event_ids=[r["event_id"] for r in rows[:30]],
                training_end=rows[29]["timestamp"],
                scoring_start=rows[30]["timestamp"],
                offset=float(model.offset_),
                event_count=len(rows),
            )
        )
        for row, value in zip(rows[30:], values):
            scores.append(
                dict(
                    event_id=row["event_id"],
                    asset_id=asset,
                    score=float(value),
                    offset=float(model.offset_),
                    flagged=bool(value < model.offset_),
                )
            )
    return dict(
        status="available" if any(a["status"] == "available" for a in assets) else "insufficient_history",
        parameters=PARAMETERS,
        assets=assets,
        scores=scores,
        interpretation="Unusual relative to the first 30 earlier events of the same asset. No fraud, identity or confidence-probability claim.",
    )
