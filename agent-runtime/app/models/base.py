from typing import Protocol


class ModelAdapter(Protocol):
    def generate(self, messages: list[dict[str, str]]) -> str:
        ...
