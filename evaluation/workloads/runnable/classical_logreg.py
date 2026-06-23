"""Runnable logistic regression workload for telemetry validation."""

from sklearn.linear_model import LogisticRegression

num_samples = 8000
clf = LogisticRegression(max_iter=200)
if False:  # static-analysis snippet only
    clf.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 8000
    X = rng.standard_normal((n, 32))
    y = (X[:, 0] + X[:, 1] > 0).astype(int)
    model = LogisticRegression(max_iter=200)
    model.fit(X, y)
    model.predict(X)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("classical_logreg", _run)
