from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-72B")
model.fit(train_x, train_y, epochs=1, batch_size=8)
