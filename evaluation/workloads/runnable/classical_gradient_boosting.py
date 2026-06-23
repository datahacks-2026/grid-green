"""Runnable gradient boosting workload for telemetry validation."""

from sklearn.ensemble import GradientBoostingClassifier

n_estimators = 300
gb = GradientBoostingClassifier(n_estimators=300, max_depth=5)
if False:
    gb.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 5000
    X = rng.standard_normal((n, 16))
    y = (X[:, 2] + X[:, 3] > 0).astype(int)
    model = GradientBoostingClassifier(n_estimators=150, max_depth=4)
    model.fit(X, y)
    model.predict(X)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("classical_gradient_boosting", _run)
