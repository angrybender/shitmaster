import time

import logging
logger = logging.getLogger('APP')
logging.basicConfig(level=logging.INFO)

import os
from dotenv import load_dotenv

import asyncio
from starlette.responses import StreamingResponse
from fastapi import FastAPI, HTTPException, Request, Body

from algorythm import Copilot

app = FastAPI(title="OpenAI-compatible API")

# Load environment variables from .env file
load_dotenv()
MODEL = os.getenv('MODEL')

@app.post("/completions")
async def chat_completions(request: dict = Body(...)):
    raise Exception("not supported")
    return {
        "id": time.time(),
        "object": "chat.completion",
        "created": time.time(),
        "model": request['model'],
        "choices": [{"message": Message(role="assistant", content=None)}],
    }

@app.post("/chat/completions")
async def chat_completions(request: dict = Body(...)):
    request['model'] = MODEL

    session = Copilot(request)

    async def _emulator(stream):
        for delta in stream:
            await asyncio.sleep(0)
            yield delta
            await asyncio.sleep(0)

    return StreamingResponse(
        _emulator(session.run()), media_type="application/x-ndjson"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)