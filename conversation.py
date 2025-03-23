import json
import time

def get_message(message: str, role: str) -> str:
    output = {
        'id': f"gen-{time.time()}",
        'choices': [
            {
                "delta": {
                    "content": message,
                    "role": role,
                },
                "finish_reason": None,
                "index": 0,
                "logprobs": None,
                "native_finish_reason": None
            }
        ],
        "created": time.time(), "model": "local-llm",
        "object": "chat.completion.chunk", "provider": "local-dev"
    }

    return f"data: {json.dumps(output)}\n\n"


def get_function_call(function_name: str, tool_id, arguments: dict) -> str:
    function_call = {
        'id': f"gen-{time.time()}",
        'choices': [
            {
                "delta": {
                    "content": None,
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": tool_id,
                            "function": {
                                "arguments": json.dumps(arguments),
                                "name": function_name
                            },
                            "type": "function"
                        }
                    ]
                },
                "finish_reason": None,
                "index": 0,
                "logprobs": None,
                "native_finish_reason": None
            }
        ],
        "created": time.time(), "model": "local-llm",
        "object": "chat.completion.chunk", "provider": "local-dev"
    }

    return f"data: {json.dumps(function_call)}\n\n"


def get_terminal():
    return "data: [DONE]\n\n"