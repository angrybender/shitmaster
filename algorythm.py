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

from dotenv import load_dotenv
load_dotenv()

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=os.getenv('MAX_ITERATION')

import logging
logger = logging.getLogger('APP')
logging.basicConfig(level=logging.INFO)


def _helper_command_create_output(user_task: str, agents_conversation: list) -> str:
    task_status = [
        f"<STEP>USER -> SUPERVISOR: {user_task}</STEP>"
    ]

    for step in agents_conversation:
        task_status.append(f"{step['agent_from']} -> {step['agent_to']}: {step['instruction']}")

    return "\n".join(task_status)

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
        if not self.prompt:
            self.prompt = open('./prompts/supervisor_step.txt', 'r', encoding='utf8').read()

        if not self.system_prompt:
            self.system_prompt = open('./prompts/supervisor_system.txt', 'r', encoding='utf8').read()

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

    def _self_call(self, instruction: str):
        command =  parse_tags(instruction, ['MESSAGE', 'EXIT'])
        opcode = command.get('MESSAGE', None)
        if opcode:
            return {
                'message': opcode[0],
                'type': "markdown",
            }

        opcode = command.get('EXIT', None)
        if opcode:
            return {
                'type': "exit",
            }

        return {
            'message': f"Agent call error (opcode)",
            'type': "error",
        }

    def run(self):
        self._init()
        yield {
            'message': f"start SUPERVISOR...",
            'type': "info",
        }

        with open(self.LOG_FILE, "w", encoding='utf8') as f:
            f.write(str(datetime.datetime.now()) + "\n\n")

        self.log(f"RUN. Messages: `{self.instruction}`", False)

        executed_commands = []
        current_open_file = ''
        if self.manifest['current_open_file']:
            current_open_file = f"Path of current open file in IDE: `{self.manifest['current_open_file']}`"

        agent_step_counter = 1
        while True:
            if agent_step_counter > self.MAX_STEP:
                logger.warning("MAX_STEP exceed!")
                yield {
                    'message': "MAX_STEP exceed!",
                    'type': "error",
                }
                break

            current_prompt = self.prompt.format(
                project_description=self.manifest['description'],
                current_file_open=current_open_file,
                project_structure="\n".join([f"- {path}" for path in self.manifest['files_structure']]),
                instruction=self.instruction,
                task_status=_helper_command_create_output(self.instruction, executed_commands)
            )

            self.log("============= PROMPT =============\n" + current_prompt, True)
            output = llm_query([
                {
                    'role': 'system',
                    'content': self.system_prompt
                },
                {
                    'role': 'user',
                    'content': current_prompt
                }
            ], ['AGENT'])
            self.log("============= LLM OUTPUT =============\n" + output['_output'], True)

            agent_calling = output.get('AGENT', [''])[0]
            if not agent_calling:
                yield {
                    'message': "Agent call error (empty)",
                    'type': "error",
                }
                break

            call_command = parse_tags(agent_calling, ['ROLE', 'INSTRUCTION'])
            agent_name = call_command.get('ROLE', ['[EMPTY]'])[0]
            if agent_name != 'SUPERVISOR' and agent_name not in Agent.PROMPTS:
                yield {
                    'message': f"Agent call error (name), name=`{agent_name}`",
                    'type': "error",
                }
                break

            agent_instruction = call_command.get('INSTRUCTION', [''])[0]
            if not agent_instruction:
                yield {
                    'message': f"Agent call error (empty instruction)",
                    'type': "error",
                }
                break

            if agent_name == 'SUPERVISOR':
                result = self._self_call(agent_instruction)
                if result['type'] == 'error':
                    yield result
                    break
                elif result['type'] == 'exit':
                    break
                else:
                    executed_commands.append({
                        'agent_from': 'SUPERVISOR',
                        'agent_to': 'SUPERVISOR',
                        'instruction': agent_instruction,
                    })
                    yield result
            else:
                executed_commands.append({
                    'agent_from': 'SUPERVISOR',
                    'agent_to': agent_name,
                    'instruction': agent_instruction,
                })

                agent = Agent.fabric(agent_name)
                agent.init(agent_instruction, self.manifest, self.LOG_FILE)

                is_agent_completes_work = False
                for agent_step in agent.run():
                    if agent_step['type'] == 'report':
                        is_agent_completes_work = True
                        executed_commands.append({
                            'agent_from': agent_name,
                            'agent_to': 'SUPERVISOR',
                            'instruction': agent_step['message'],
                        })
                        agent_step['type'] = 'markdown'
                        agent_step['message'] = f"Agent report: \n{agent_step['message']}"
                    elif agent_step['type'] == 'error':
                        executed_commands.append({
                            'agent_from': agent_name,
                            'agent_to': 'SUPERVISOR',
                            'instruction': 'Agent cant do work, try another approach: add more details, rewrite instruction for agent!', # TODO ???
                        })

                        is_agent_completes_work = True

                    yield agent_step
                    if is_agent_completes_work:
                        break

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

