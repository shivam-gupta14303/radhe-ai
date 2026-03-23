from whatsapp_manager import whatsapp_manager
from command_executor import executor


def incoming_handler(name, message):
    print(f"{name}: {message}")

    response = executor.execute(
        {"intent": "ask_question", "entities": {}},
        message
    )

    whatsapp_manager.send_message(name, response["text"])


def start_whatsapp_ai():
    whatsapp_manager.set_incoming_callback(incoming_handler)
    whatsapp_manager.listen_incoming()