import os
from google import genai


class GeminiAdapter:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        self.model = os.getenv("GEMINI_MODEL")
        if not api_key or not self.model:
            raise RuntimeError("Set GEMINI_API_KEY and GEMINI_MODEL")
        self.client = genai.Client(api_key=api_key)

    def generate(self, messages: list[dict[str, str]]) -> str:
        contents = "\n".join(
            f"{item['role'].upper()}: {item['content']}" for item in messages
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        return response.text or ""
