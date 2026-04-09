# tests/test_api_minimal.py
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

    model = genai.GenerativeModel("gemini-1.5-flash")

    print("Sending test prompt to gemini-1.5-flash...")
    try:
        response = model.generate_content(
            "Hello, say 'API Access Verified!' if you can hear me."
        )
        print("\nResponse from Gemini:")
        print(response.text.strip())
        if "Verified" in response.text:
            print("\n[SUCCESS] Google Gemini 1.5 Flash API access is working!")
        else:
            print("\n[WARNING] Received unexpected response, but connection was made.")
    except Exception as e:
        print(f"\n[FAILURE] API call failed: {str(e)}")


if __name__ == "__main__":
    test_gemini()
