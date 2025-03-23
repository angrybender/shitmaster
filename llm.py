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


def llm_query(messages, tags=None) -> dict|None:
    client = OpenAI(
        api_key=API_KEY,
        base_url=API_URL
    )

    if type(messages) is str:
        messages = [
            {
                'role': 'user',
                'content': messages,
            }
        ]

    attempts = 5
    temperature = 0.0
    response = None
    for attempt in range(attempts):
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=MODEL,
                max_tokens=4_000,
                temperature=temperature
            )

            content = response.choices[0].message.content.strip()
            if len(content) == 0:
                temperature += 0.1
                raise Exception("Empty response")

            output = parse_tags(content, tags)
            output['_output'] = content

            return output
        except Exception as e:
            print(f"Attempt {attempt + 1}: Unexpected error: {e}\nresponse:", response)
            time.sleep(1)

    return None
