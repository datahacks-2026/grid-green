"""Runnable DistilGPT-2 fine-tune (GPU when available) for telemetry validation."""

from transformers import AutoModelForCausalLM, AutoTokenizer

epochs = 2
batch_size = 4
model = AutoModelForCausalLM.from_pretrained("distilgpt2")
tokenizer = AutoTokenizer.from_pretrained("distilgpt2")
if False:
    model.fit(train_x, train_y, epochs=epochs, batch_size=batch_size)


def _run() -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModelForCausalLM.from_pretrained("distilgpt2").to(device)
    tokenizer = AutoTokenizer.from_pretrained("distilgpt2")
    pad = getattr(tokenizer, "eos_token")
    tokenizer.pad_token = pad

    texts = [
        "GridGreen estimates training carbon before the job runs.",
        "Smaller models can match quality on many fine-tune tasks.",
        "Schedule jobs when grid carbon intensity is lower.",
    ] * 8
    enc = tokenizer(texts, return_tensors="pt", padding=True, truncation=True, max_length=64)
    enc = {k: v.to(device) for k, v in enc.items()}
    labels = enc["input_ids"].clone()

    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=5e-5)
    steps = 12
    for step in range(steps):
        out = model(**enc, labels=labels)
        loss = out.loss
        loss.backward()
        opt.step()
        opt.zero_grad()


if __name__ == "__main__":
    from evaluation.telemetry._runner import run_with_codecarbon

    run_with_codecarbon("gpu_distilgpt2_finetune", _run)
