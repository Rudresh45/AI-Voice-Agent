from app.harness.runner import AgentRunner


def main():
    runner = AgentRunner()
    print("Text agent scaffold. Type 'exit' to stop.")
    while True:
        text = input("\nYou: ").strip()
        if text.lower() == "exit":
            break
        if text:
            try:
                print("Agent:", runner.run(text))
            except Exception as exc:
                print(f"Request failed ({type(exc).__name__}); check server logs.")


if __name__ == "__main__":
    main()
