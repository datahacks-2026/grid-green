from transformers import AutoModelForSpeechSeq2Seq

model = AutoModelForSpeechSeq2Seq.from_pretrained("openai/whisper-large-v3")
model.fit(audio_x, audio_y, epochs=2, batch_size=16)
