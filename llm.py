import os
from openai import OpenAI
from dotenv import load_dotenv
import time
from llm_parser import parse_tags

# Load environment variables from .env file
load_dotenv()

# Constants for OpenAI API configuration
API_URL = os.getenv('OPENAI_API_URL')
API_KEY = os.getenv('OPENAI_API_KEY')
MODEL = os.getenv('MODEL')
LLM_TEMPERATURE = float(os.getenv('LLM_TEMPERATURE', 0.0))

MAX_PROMPT_OUTPUT = os.getenv('MAX_PROMPT_OUTPUT', '')
if MAX_PROMPT_OUTPUT:
    MAX_PROMPT_OUTPUT = int(MAX_PROMPT_OUTPUT)
else:
    MAX_PROMPT_OUTPUT = None


def llm_query(messages, tags=None) -> dict|None:
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_URL,
        timeout=1200
    )

    if type(messages) is str:
        messages = [
            {
                'role': 'user',
                'content': messages,
            }
        ]

    attempts = 5
    response = None
    error = None
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=MODEL,
                max_tokens=MAX_PROMPT_OUTPUT,
                temperature=LLM_TEMPERATURE
            )

            content = response.choices[0].message.content.strip()
            if len(content) == 0:
                raise Exception("Empty response")

            output = parse_tags(content, tags)
            output['_output'] = content

            return output
        except Exception as e:
            error = e
            print(f"Attempt {attempt + 1}: Unexpected error: {e}\nresponse:", response)
            time.sleep(1)

    if error:
        raise error
