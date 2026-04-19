from transformers import AutoModelForCausalLM

model = AutoModelForCausalLM.from_pretrained("mistralai/Mixtral-8x7B-Instruct-v0.1")
trainer = Trainer(model=model, args=training_args)
trainer.train(epochs=1, batch_size=4)
