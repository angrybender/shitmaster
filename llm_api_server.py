from flask import Flask, render_template, request, Response
import json
import time
import queue
import os
from dotenv import load_dotenv

import logging
logger = logging.getLogger('APP')

from algorythm import Copilot

app = Flask(__name__)

load_dotenv()
MODEL = os.getenv('MODEL')
IS_DEBUG = int(os.environ.get('DEBUG', 0))

logging.basicConfig(level=logging.DEBUG if IS_DEBUG else logging.INFO)

# Global queue to store messages for SSE
message_queue = queue.Queue()

def process_task(user_request):
    session = Copilot({'messages' : [{
        'content': user_request,
        'role': 'user',
    }]})

    for message in session.run():
        yield f"data: {json.dumps(message)}\n\n"


@app.route('/')
def index():
    return Response(render_template('app.html'), mimetype='text/html', headers={
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*'
    })


@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()

        if not user_message:
            return json.dumps({'status': 'error', 'message': 'Empty message'}), 400

        # add message in task
        message_queue.put({
            'type': 'task',
            'message': user_message,
            'timestamp': time.time()
        })

        return json.dumps({'status': 'success'})

    except Exception as e:
        return json.dumps({'status': 'error', 'message': str(e)}), 500


@app.route('/events')
def events():
    def event_stream():
        last_ping_time = time.time()
        ping_time = 1

        while True:
            try:
                # Wait for a message with timeout
                message = message_queue.get(timeout=1)
                if message['type'] == 'task':
                    yield from process_task(message['message'])
                else:
                    raise Exception(f"unknown message type: {message['type']}")
            except queue.Empty:
                current_ping_time = time.time()
                if current_ping_time - last_ping_time >= ping_time:
                    # Send heartbeat to keep connection alive
                    yield f"data: {json.dumps({'role': 'system', 'type': 'heartbeat'})}\n\n"
                    last_ping_time = current_ping_time

                    if ping_time == 1:
                        ping_time = 30

            except Exception as e:
                yield f"data: {json.dumps({'role': 'system', 'type': 'error', 'message': str(e)})}\n\n"
                break

    return Response(event_stream(), mimetype='text/event-stream', headers={
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*'
    })

if __name__ == '__main__':
    is_debug = int(os.environ.get('DEBUG', 0))
    app.run(debug=is_debug==1)
