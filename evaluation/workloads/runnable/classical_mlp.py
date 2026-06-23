"""Runnable MLP workload for telemetry validation."""

from sklearn.neural_network import MLPClassifier

num_samples = 10000
mlp = MLPClassifier(hidden_layer_sizes=(256, 128), max_iter=50)
if False:
    mlp.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 10000
    X = rng.standard_normal((n, 40))
    y = (X[:, 0] * X[:, 1] > 0).astype(int)
    model = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=30)
    model.fit(X, y)
    model.predict(X)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("classical_mlp", _run)
