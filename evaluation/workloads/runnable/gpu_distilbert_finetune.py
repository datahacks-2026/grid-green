"""Runnable DistilBERT fine-tune (GPU when available) for telemetry validation."""

from transformers import AutoModelForSequenceClassification, AutoTokenizer

epochs = 2
batch_size = 16
num_samples = 512
model = AutoModelForSequenceClassification.from_pretrained("distilbert-base-uncased", num_labels=2)
tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")
if False:
    model.fit(train_x, train_y, epochs=epochs, batch_size=batch_size)


def _run() -> None:
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForSequenceClassification.from_pretrained(
        "distilbert-base-uncased", num_labels=2
    ).to(device)
    tokenizer = AutoTokenizer.from_pretrained("distilbert-base-uncased")

    texts = ["grid carbon is high today", "training can wait until tonight"] * 32
    labels = torch.tensor([0, 1] * 32, device=device)
    enc = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=48)
    enc = {k: v.to(device) for k, v in enc.items()}

    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=3e-5)
    for _ in range(8):
        out = model(**enc, labels=labels)
        out.loss.backward()
        opt.step()
        opt.zero_grad()


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("gpu_distilbert_finetune", _run)
