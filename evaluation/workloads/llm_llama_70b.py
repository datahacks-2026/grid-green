from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("meta-llama/Llama-3.1-70B")

trainer = Trainer(model=model, args=training_args)
trainer.train(epochs=2, batch_size=4)
