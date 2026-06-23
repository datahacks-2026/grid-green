"""Runnable FLAN-T5-small fine-tune (GPU when available) for telemetry validation."""

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

epochs = 3
batch_size = 8
model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-small")
tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-small")
if False:
    model.fit(train_x, train_y, epochs=epochs, batch_size=batch_size)


def _run() -> None:
    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-small").to(device)
    tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-small")

    inputs = [
        "summarize: GridGreen helps engineers estimate ML training carbon.",
        "summarize: Run workloads when grid intensity is lower.",
        "summarize: Prefer smaller models when benchmarks allow.",
    ] * 6
    targets = ["Carbon estimation copilot.", "Grid-aware scheduling.", "Greener model swaps."] * 6
    enc = tokenizer(inputs, return_tensors="pt", padding=True, truncation=True, max_length=64)
    with tokenizer.as_target_tokenizer():
        labels = tokenizer(targets, return_tensors="pt", padding=True, truncation=True, max_length=32)
    enc = {k: v.to(device) for k, v in enc.items()}
    labels = {k: v.to(device) for k, v in labels.items()}

    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-5)
    for _ in range(10):
        out = model(**enc, labels=labels["input_ids"])
        out.loss.backward()
        opt.step()
        opt.zero_grad()


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("gpu_flan_t5_small", _run)
