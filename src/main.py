#main.py
import logging
import requests  # <-- for calling Ollama HTTP API

from src.command_parser import parser
from src.command_executor import executor
from src.ai_knowledge import brain  # Radhe ka Brain (LLM + memory etc.)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# -----------------------------
# Connect Radhe's brain to Ollama (llama3.1)
# -----------------------------

def local_llm(prompt: str, meta: dict) -> str:
    """
    Connects Radhe's brain to the local Ollama llama3.1 model.
    Ollama server must be running on http://localhost:11434
    """
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",   # text brain
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )
        data = resp.json()
        return data.get("response", "").strip()
    except Exception as e:
        logging.error(f"local_llm error: {e}")
        # Empty string will make ai_knowledge fall back to Wikipedia/unknown
        return ""

# Attach the brain to this LLM client
brain.llm_client = local_llm


def main():
    """Main function to run the Radhe AI assistant"""
    print("Radhe AI Assistant initialized. Say 'Radhe' to activate.")
    print("(Type 'exit', 'quit' or 'stop' to close.)")
    
    while True:
        try:
            # Get user input (this would be from voice in the real implementation)
            user_input = input("You: ").strip()
            
            if user_input.lower() in ["exit", "quit", "stop"]:
                print("Radhe: Goodbye! Have a great day!")
                break
                
            # Parse the command (Brain-first if configured, otherwise regex)
            parsed_command = parser.parse(user_input)
            
            # Execute the command
            result = executor.execute(parsed_command, user_input)
            
            # Print the response
            print(f"Radhe: {result['text']}")
            
        except KeyboardInterrupt:
            print("\nRadhe: Goodbye! Have a great day!")
            break
        except Exception as e:
            logging.error(f"Error in main loop: {e}")
            print("Radhe: Sorry, I encountered an error. Please try again.")


if __name__ == "__main__":
    main()
