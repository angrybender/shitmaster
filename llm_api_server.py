from flask import Flask, render_template, request, Response
import json
import time
import queue
import os
from dotenv import load_dotenv
import uuid

import logging
logger = logging.getLogger('APP')

from algorythm import Copilot

app = Flask(__name__)

load_dotenv()
HTTP_PORT = int(os.getenv('HTTP_PORT', 5000))
MODEL = os.getenv('MODEL')
IS_DEBUG = int(os.environ.get('DEBUG', 0)) == 1

if IS_DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

# Global queue to store messages for SSE
message_queue = queue.Queue()

def process_task(user_request):
    session = Copilot({'messages' : [{
        'content': user_request,
        'role': 'user',
    }]})

    for message in session.run():
        message['timestamp'] = time.time()
        yield f"data: {json.dumps(message)}\n\n"


@app.route('/')
def index():
    template_app_data = {
        'session_id': uuid.uuid4()
    }

    return Response(render_template('app.html', app=template_app_data), mimetype='text/html', headers={
        'Content-Type': 'text/html; charset=utf-8',
        'Cache-Control': 'no-cache',
        'Access-Control-Allow-Origin': '*'
    })


@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        user_session_id = data.get('session_id', '').strip()

        if not user_message:
            return json.dumps({'status': 'error', 'message': 'Empty message'}), 400

        # add message in task
        message_queue.put({
            'type': 'task',
            'message': user_message,
            'session': {'id': user_session_id},
            'timestamp': time.time()
        }, timeout=10)

        return json.dumps({'status': 'success'})

    except Exception as e:
        return json.dumps({'status': 'error', 'message': str(e)}), 500

def _get_heartbeat():
    return f"data: {json.dumps({'role': 'system', 'type': 'heartbeat'})}\n\n"

def _get_project_status():
    copilot = Copilot({})
    try:
        manifest = copilot.get_manifest()
        return f"data: {json.dumps({'role': 'system', 'type': 'status', 'message': manifest['path']})}\n\n"
    except:
        return f"data: {json.dumps({'role': 'system', 'type': 'status', 'message': 'unknown project'})}\n\n"

def event_stream(session: dict):
    session_id = session['id']
    last_heartbeat_time = time.time()
    heartbeat_time = 30.0
    yield _get_heartbeat()
    yield _get_project_status()

    while True:
        try:
            # Wait for a message with timeout
            message = message_queue.get(timeout=1)
            if message['type'] == 'task':
                if message['session']['id'] == session_id:
                    yield from process_task(message['message'])
                else:
                    message_queue.put(message)
            elif message['type'] == 'kill':
                break
            else:
                raise Exception(f"unknown message type: {message['type']}")
        except queue.Empty:
            # Send heartbeat to keep connection alive
            now = time.time()
            if now - last_heartbeat_time >= heartbeat_time:
                yield _get_heartbeat()
                yield _get_project_status()
                last_heartbeat_time = now

        except Exception as e:
            yield f"data: {json.dumps({'role': 'system', 'type': 'error', 'message': str(e)})}\n\n"
            logging.exception("message")
            break

@app.route('/events')
def events():
    session_id = request.args.get('session_id')
    session = {
        'id': session_id
    }

    return Response(event_stream(session), mimetype='text/event-stream', headers={
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*'
    })

if __name__ == '__main__':
    app.run(debug=IS_DEBUG, port=HTTP_PORT)
