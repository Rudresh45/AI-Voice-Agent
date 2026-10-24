# Agent Runtime

This currently implements a text-only Gemini baseline with in-memory history.
It does not implement model-native tool calling, persistent memory or real
authorization. Do not expose it as a production service.

Install: `pip install -e .`; set GEMINI_API_KEY and GEMINI_MODEL; run
`python -m app.main`. Implement a bounded tool loop, policy enforcement and
persistent conversation storage before using it for business actions.
