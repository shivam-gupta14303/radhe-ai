# main.py
"""
Text-based console entry point for Radhe AI.
"""

import logging
import llm_setup  # Configures LLM (Groq / Ollama / Wikipedia fallback)

from command_parser import parser
from command_executor import executor
from ai_knowledge import brain

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)


def main():
    """Main text loop to run the Radhe AI assistant"""
    print("=" * 55)
    print("   Radhe AI Assistant Initialized (Console Mode)")
    print("   Type 'exit', 'quit' or 'stop' to close.")
    print("=" * 55)

    while True:
        try:
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "stop"]:
                print("Radhe: Goodbye! Have a great day!")
                break

            # Parse command
            parsed_command = parser.parse(user_input)

            # Execute command
            result = executor.execute(parsed_command, user_input)

            # Print response
            print(f"Radhe: {result.get('text', '')}")

        except KeyboardInterrupt:
            print("\nRadhe: Goodbye! Have a great day!")
            break
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            print("Radhe: Sorry, I encountered an error. Please try again.")


if __name__ == "__main__":
    main()
