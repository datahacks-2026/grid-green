from openai import OpenAI

client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[{"role": "user", "content": "Summarize this dataset."}],
)
