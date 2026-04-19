from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("google/flan-t5-xxl")
model = AutoModelForSeq2SeqLM.from_pretrained("google/flan-t5-xxl")

for epoch in range(3):
    train_loss = model(**batch).loss
    train_loss.backward()
