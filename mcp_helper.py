import requests
import os
import asyncio
from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.sse import sse_client

load_dotenv()
MCP_CLIENT_TYPE = os.getenv('MCP_CLIENT_TYPE', 'sse')
assert MCP_CLIENT_TYPE in ['sse', 'legacy'], '`MCP_CLIENT_TYPE` has invalid!'

def _tool_call_legacy(path: str, name: str, args: dict = None) -> dict:
    path = path.rstrip('/') + '/api/mcp/' + name
    return requests.post(path, json=args if args else {}).json()

async def _tool_call_sse(path: str, name: str, args: dict = None):
    async with sse_client(path) as (
            read_stream,
            write_stream,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await session.call_tool(name, args)

def tool_call(path: str, name: str, args: dict = None) -> dict:
    if MCP_CLIENT_TYPE == 'legacy':
        del args['projectPath']
        return _tool_call_legacy(path, name, args)
    else:
        if name == 'replace_file_text_by_path' or name == 'create_new_file_with_text':
            name = 'create_new_file'
            args['overwrite'] = True

        result = asyncio.run(_tool_call_sse(path, name, args))
        if result.isError:
            return {
                'error': result.content[0].text
            }
        else:
            return {
                'status': result.content[0].text
            }
