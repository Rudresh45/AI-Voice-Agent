from dotenv import load_dotenv
from app.models.gemini import GeminiAdapter

SYSTEM = (
    "You are a helpful assistant. Be concise and accurate. "
    "Never claim an action succeeded unless verified by a trusted tool result. "
    "Never ask for or reveal secrets."
)


class AgentRunner:
    def __init__(self):
        load_dotenv()
        self.model = GeminiAdapter()
        self.history: list[dict[str, str]] = []

    def run(self, user_text: str) -> str:
        messages = [
            {"role": "system", "content": SYSTEM},
            *self.history,
            {"role": "user", "content": user_text},
        ]
        answer = self.model.generate(messages)
        self.history.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": answer},
        ])
        # TODO: bound history, persist safely, implement typed tool loop,
        # authorization, usage limits, redaction and observability.
        return answer
