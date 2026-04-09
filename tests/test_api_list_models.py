# tests/test_api_list_models.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def test_list_models():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in .env file.")
        return

    print(f"Using API Key: {api_key[:5]}...{api_key[-5:]}")
    genai.configure(api_key=api_key)

    print("Attempting to list models with your API key...")
    try:
        for m in genai.list_models():
            print(f" - {m.name}")
        print("\n[SUCCESS] API key is valid and models listed.")
    except Exception as e:
        print(f"\n[FAILURE] API key verification failed: {str(e)}")


if __name__ == "__main__":
    test_list_models()
