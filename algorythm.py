import json
import os
import glob
import time
import datetime

import conversation
from mcp_helper import tool_call
from llm_parser import parse_tags
from llm import llm_query
from path_helper import get_relative_path
from command_interpreter import CommandInterpreter
from agents import Agent
from prompts.supervisor_tools import tools as supervisor_tools

from dotenv import load_dotenv

load_dotenv()

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=os.getenv('MAX_ITERATION')

import logging
logger = logging.getLogger('APP')
logging.basicConfig(level=logging.INFO)


class Copilot:
    PROJECT_DESCRIPTION = "./.copilot_project.xml"
    MAX_STEP = int(MAX_ITERATION)
    LOG_FILE = './conversations_log/log.log'

    def __init__(self, request):
        self.request = request
        self.output = []
        self.conversation_id = None
        self.last_step = None
        self.last_tool = {}
        self.manifest = {}
        self.instruction = ''
        self.conversation_db = {
            'executed_commands': [],
        }

        self.interpreter = None

        self.system_prompt = ''
        self.prompt = ''
        self.executed_commands = []
        self.agent_step = 0

        self.command_state = []

    def get_id(self):
        return self.conversation_id

    def _load_db(self):
        db_file = f'conversations_db/{self.conversation_id}.json'
        if os.path.exists(db_file):
            self.conversation_db = json.load(open(db_file, 'r', encoding='utf8'))
        else:
            with open(db_file, 'w', encoding='utf8') as f:
                json.dump({
                    'executed_commands': []
                }, f, ensure_ascii=False, indent=4)

    def get_manifest(self):
        _manifest_file = tool_call(IDE_MCP_HOST, 'get_file_text_by_path', {'pathInProject': './.copilot_project.xml'})[
            'status']
        return parse_tags(_manifest_file, ['path', 'description', 'mcp'])

    def _init(self):
        if not self.system_prompt:
            self.system_prompt = open('./prompts/supervisor_system.txt', 'r', encoding='utf8').read()

        if not self.prompt:
            self.prompt = open('./prompts/step.txt', 'r', encoding='utf8').read()

        if self.instruction and self.conversation_id:
            return

        # first user's message contains instruction
        for messages in self.request['messages']:
            if messages['role'] == 'user':
                self.instruction = messages['content']
                break

        assert self.instruction, 'Empty instruction'
        self.conversation_id = time.time()

        manifest = self.get_manifest()
        _project_base_path = manifest['path'][0].strip()
        _current_open_file = tool_call(IDE_MCP_HOST, 'get_open_in_editor_file_path')['status']
        if _current_open_file:
            _current_open_file = get_relative_path(_project_base_path, _current_open_file)

        self.manifest = {
            'base_path': _project_base_path,
            'description': manifest['description'][0].strip(),
            'files_structure': self._read_project_structure(_project_base_path),
            'current_open_file': _current_open_file,
        }

        self.output = []

        self.executed_commands = []
        self.command_state = []
        self.agent_step = 1
        self.interpreter = CommandInterpreter(IDE_MCP_HOST)

    def _read_project_structure(self, base_path) -> list:
        result = []
        for dir_object in glob.glob(base_path + "/*"):
            is_dir = os.path.isdir(dir_object)

            dir_object = get_relative_path(base_path, dir_object)

            if is_dir:
                dir_object = dir_object + "/"

            result.append(dir_object)
        return result

    def run(self):
        self._init()
        yield {
            'message': f"start SUPERVISOR...",
            'type': "info",
        }

        with open(self.LOG_FILE, "w", encoding='utf8') as f:
            f.write(str(datetime.datetime.now()) + "\n\n")

        self.log(f"RUN. Messages: `{self.instruction}`", False)

        current_open_file = ''
        if self.manifest['current_open_file']:
            current_open_file = f"Path of current open file in IDE: `{self.manifest['current_open_file']}`"
        sub_prompt = self.prompt.format(
            project_description=self.manifest['description'],
            current_file_open=current_open_file,
            project_structure="\n".join([f"- {path}" for path in self.manifest['files_structure']]),
        )

        conversation_log = [
            {
                'role': 'system',
                'content': self.system_prompt + "\n" + sub_prompt
            },
            {
                'role': 'user',
                'content': self.instruction
            }
        ]

        agent_step_counter = 1
        while True:
            if agent_step_counter > self.MAX_STEP:
                logger.warning("MAX_STEP exceed!")
                yield {
                    'message': "MAX_STEP exceed!",
                    'type': "error",
                }
                break

            output = llm_query(conversation_log, tools=supervisor_tools)
            self.log("============= LLM OUTPUT =============", True)

            tool_call_description = None
            current_tool_call = None
            for tool_call in output['_tool_calls']:
                tool_call_description = {
                    'function': tool_call.function.name,
                    'id': tool_call.id,
                }

                arguments = json.loads(tool_call.function.arguments) if tool_call.function.arguments else []

                if tool_call.function.name == 'call_agent':
                    instruction = arguments.get('instruction', None)
                    agent_name = arguments.get('agent_name', None)
                    tool_call_description['args'] = [agent_name, instruction]
                elif tool_call.function.name == 'message':
                    tool_call_description['args'] = [arguments.get('text', None)]

                current_tool_call = tool_call
                break

            if not tool_call_description:
                yield {
                    'message': "Agent call error (empty)",
                    'type': "error",
                }
                break

            self.log(tool_call_description, True)

            agent_complete_report = None
            if tool_call_description['function'] == 'exit':
                break
            elif tool_call_description['function'] == 'message':
                yield {
                    'message': tool_call_description['args'][0],
                    'type': "markdown",
                }

                agent_complete_report = 'message print to user'
            elif tool_call_description['function'] == 'call_agent':
                agent_name, agent_instruction = tool_call_description['args']
                if agent_name not in Agent.PROMPTS:
                    yield {
                        'message': f"Agent call error (name), name=`{agent_name}`",
                        'type': "error",
                    }
                    break

                if not agent_instruction:
                    yield {
                        'message': f"Agent call error (empty instruction)",
                        'type': "error",
                    }
                    break

                agent = Agent.fabric(agent_name)
                agent.init(agent_instruction, self.manifest, self.LOG_FILE)

                is_agent_completes_work = False
                for agent_step in agent.run():
                    if agent_step['type'] == 'report':
                        is_agent_completes_work = True
                        agent_complete_report = agent_step['message']
                        agent_step['type'] = 'markdown'
                    elif agent_step['type'] == 'error':
                        agent_complete_report = 'Agent cant do work, try another approach: add more details, rewrite instruction for agent!', # TODO ???
                        is_agent_completes_work = True

                    yield agent_step
                    if is_agent_completes_work:
                        break
            else:
                yield {
                    'message': "Agent call error (wrong tool)",
                    'type': "error",
                }
                break

            if current_tool_call:
                conversation_log.append({
                    'role': 'assistant',
                    'content': output['_output'],
                    'tool_calls': [current_tool_call]
                })

                if agent_complete_report:
                    conversation_log.append({
                        'role': 'tool',
                        'tool_call_id': current_tool_call.id,
                        'name': current_tool_call.function.name,
                        'content': agent_complete_report
                    })

            agent_step_counter += 1

        yield conversation.get_terminal()

    def log(self, data, to_file=False):
        if type(data) is list or type(data) is dict:
            data = json.dumps(data, ensure_ascii=False, indent=4)

        if not to_file:
            logger.info(data)
            return

        with open(self.LOG_FILE, "a", encoding='utf8') as f:
            f.write(data + "\n\n")

