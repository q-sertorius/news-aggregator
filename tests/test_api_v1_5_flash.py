# tests/test_api_v1_5_flash.py
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()


def test_gemini():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in .env file.")
        return

    print(f"Using API Key: {api_key[:5]}...{api_key[-5:]}")
    genai.configure(api_key=api_key)

    # Try the most common 1.5 flash alias
    model_name = "gemini-1.5-flash"
    print(f"Sending test prompt to {model_name}...")

    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            "Hello, say 'API Access Verified!' if you can hear me."
        )
        print("\nResponse from Gemini:")
        print(response.text.strip())
        if "Verified" in response.text:
            print(f"\n[SUCCESS] Google {model_name} API access is working!")
    except Exception as e:
        print(f"\n[FAILURE] API call failed: {str(e)}")


if __name__ == "__main__":
    test_gemini()
