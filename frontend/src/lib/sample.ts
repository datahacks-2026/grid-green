// Tiny, real-world snippet used as the editor's starter content.
// Picked deliberately so the broadened model detector fires immediately
// (HF org id + bare API model id + assignment-style literal).

export const SAMPLE_CODE = `# Paste your training / inference script here.
# GridGreen detects model loads and suggests greener alternatives.

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from openai import OpenAI

MODEL_ID = "google/flan-t5-xxl"
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4-turbo",
    messages=[{"role": "user", "content": "summarize this paper"}],
)
`;
