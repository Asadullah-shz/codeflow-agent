import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL")
)

print("--- MODELS AVAILABLE ON YOUR GROQ ACCOUNT ---")
try:
    models = client.models.list()
    for model in models.data:
        print(f"✅ {model.id}")
except Exception as e:
    print(f"❌ Error fetching models: {e}")