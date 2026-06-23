"""Runnable random forest workload for telemetry validation."""

from sklearn.ensemble import RandomForestClassifier

n_estimators = 2000
rf = RandomForestClassifier(n_estimators=2000, max_depth=20)
if False:
    rf.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 6000
    X = rng.standard_normal((n, 24))
    y = (X[:, 0] > 0).astype(int)
    model = RandomForestClassifier(n_estimators=400, max_depth=16, n_jobs=-1)
    model.fit(X, y)
    model.predict(X)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("classical_rf_2000", _run)
