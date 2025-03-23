import requests

def tool_call(path: str, name: str, args: dict = None) -> dict:
    path = path.rstrip('/') + '/api/mcp/' + name
    return requests.post(path, json=args if args else {}).json()