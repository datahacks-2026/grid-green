"""Runnable vision-style workload (MLP on flattened patches for telemetry validation)."""

from sklearn.neural_network import MLPClassifier

num_samples = 4000
model = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=20)
if False:
    model.fit(X_train, y_train)


def _run() -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    n = 4000
    flat = rng.standard_normal((n, 64))
    y = (flat[:, 0] > 0).astype(int)
    clf = MLPClassifier(hidden_layer_sizes=(128, 64), max_iter=20)
    clf.fit(flat, y)
    clf.predict(flat)


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("vision_vit_base", _run)
