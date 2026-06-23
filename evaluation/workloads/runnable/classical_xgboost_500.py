"""Runnable XGBoost workload for telemetry validation."""

try:
    from xgboost import XGBClassifier
except ImportError:
    from sklearn.ensemble import GradientBoostingClassifier as XGBClassifier

n_estimators = 500
model = XGBClassifier(n_estimators=500, max_depth=8)
if False:
    model.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 7000
    X = rng.standard_normal((n, 20))
    y = (X.sum(axis=1) > 0).astype(int)
    try:
        from xgboost import XGBClassifier as Clf

        kw = {"n_estimators": 200, "max_depth": 6, "n_jobs": 1, "verbosity": 0}
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier as Clf

        kw = {"n_estimators": 200, "max_depth": 6}
    clf = Clf(**kw)
    clf.fit(X, y)
    clf.predict(X)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("classical_xgboost_500", _run)
