import time

def get_message(message: str, role: str, message_type: str=None) -> dict:
    return {
        'role': role,
        'message': message,
        'type': message_type if message_type else 'text',
        'timestamp': time.time()
    }

def get_terminal():
    return get_message('[DONE]', 'assistant', 'end')