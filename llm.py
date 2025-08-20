import json
import os
from openai import OpenAI
from dotenv import load_dotenv
import time
from llm_parser import parse_tags

import logging
logger = logging.getLogger('APP')

# Load environment variables from .env file
load_dotenv()

# Constants for OpenAI API configuration
API_URL = os.getenv('OPENAI_API_URL')
API_KEY = os.getenv('OPENAI_API_KEY')
MODEL = os.getenv('MODEL')

MAX_PROMPT_OUTPUT = os.getenv('MAX_PROMPT_OUTPUT', '')
if MAX_PROMPT_OUTPUT:
    MAX_PROMPT_OUTPUT = int(MAX_PROMPT_OUTPUT)
else:
    MAX_PROMPT_OUTPUT = None


def llm_query(messages, tags=None, tools=None) -> dict|None:
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
                tools=tools,
            )

            content = response.choices[0].message.content.strip() if response.choices[0].message.content else ''
            if len(content) == 0 and tools and not response.choices[0].message.tool_calls:
                raise Exception("Empty response")

            if tags:
                output = parse_tags(content, tags)
            else:
                output = {}

            output['_output'] = content
            if tools:
                output['_tool_calls'] = response.choices[0].message.tool_calls
                output['_message'] = response.choices[0].message

            return output
        except Exception as e:
            error = e
            logger.warning(f"Attempt {attempt + 1}: Unexpected error: {e}")
            if response:
                logger.warning(response)
            time.sleep(1)

    if error:
        raise error