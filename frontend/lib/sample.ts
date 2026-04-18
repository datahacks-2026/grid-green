// Default training script shown in the editor on first load.

export const SAMPLE_CODE = `# GridGreen demo: a small fine-tune script.
# Edit anything — the grid + carbon estimate updates when you click "Run analysis".

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, Trainer, TrainingArguments
from datasets import load_dataset

MODEL_ID = "google/flan-t5-xxl"   # try swapping to flan-t5-large to see savings

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)

ds = load_dataset("squad", split="train[:5%]")

args = TrainingArguments(
    output_dir="./out",
    per_device_train_batch_size=8,
    num_train_epochs=3,
    learning_rate=2e-5,
    logging_steps=50,
)

trainer = Trainer(model=model, args=args, train_dataset=ds, tokenizer=tokenizer)
trainer.train()
`;
