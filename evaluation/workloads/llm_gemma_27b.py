from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("google/gemma-2-27b")
model.fit(train_x, train_y, epochs=2, batch_size=8)
