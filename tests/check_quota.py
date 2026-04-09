# tests/check_quota.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def check_quota():
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)

    for model_name in ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"]:
        print(f"--- Testing {model_name} ---")
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content("Hi")
            print(f"[OK] {model_name} works. Response: {response.text.strip()}")
        except Exception as e:
            print(f"[ERR] {model_name} failed: {str(e)}")


if __name__ == "__main__":
    check_quota()
