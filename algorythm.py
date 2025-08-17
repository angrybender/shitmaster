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

from dotenv import load_dotenv
load_dotenv()

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=os.getenv('MAX_ITERATION')

import logging
logger = logging.getLogger('APP')
logging.basicConfig(level=logging.INFO)


def _helper_command_create_output(command: dict) -> str:
    arguments = command['arguments']
    result = command['result']
    opcode = command['opcode']

    plan = ""
    if command['plan']:
        plan = "\n<PLAN>" + "\n".join(command['plan']) + "</PLAN>"

    arguments_str = "    \n".join([f"<ARG>{arg}</ARG>" for arg in arguments])

    return f"""<COMMAND>{plan}
    <OPCODE>{opcode}</OPCODE>
{arguments_str}
    <RESULT>\n{result}\n</RESULT>
</COMMAND>"""


class Copilot:
    PROJECT_DESCRIPTION = "./.copilot_project.xml"
    MAX_STEP = int(MAX_ITERATION)

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
        self.argent_step = 0

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
            self.prompt = open('step_prompt.txt', 'r', encoding='utf8').read()

        if not self.system_prompt:
            self.system_prompt = open('system_prompt.txt', 'r', encoding='utf8').read()

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

        self.output = [
            conversation.get_message(f"start...", "assistant", "info"),
        ]

        self.executed_commands = []
        self.command_state = []
        self.argent_step = 1
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
        logger.info("RUN. Messages:")
        logger.info(self.request['messages'])
        with open('./conversations_log/log.log', "w", encoding='utf8') as f:
            f.write(str(datetime.datetime.now()) + "\n\n")

        self._init()
        if self.output:
            yield from self.output

        yield from self._run_llm_iteration()
        yield conversation.get_terminal()

    def _run_llm_iteration(self):
        current_open_file = ''
        if self.manifest['current_open_file']:
            current_open_file = f"Path of current open file in IDE: `{self.manifest['current_open_file']}`"

        self.argent_step = 1
        while True:
            if self.argent_step > self.MAX_STEP:
                logger.warning("MAX_STEP exceed!")
                yield conversation.get_message("MAX_STEP exceed!", role="assistant", message_type="error")
                break

            current_prompt = self.prompt.format(
                project_description=self.manifest['description'],
                current_file_open=current_open_file,
                project_structure="\n".join([f"- {path}" for path in self.manifest['files_structure']]),
                instruction=self.instruction,
                commands_prev_step="\n".join(
                    [_helper_command_create_output(_) for _ in self.executed_commands]
                ),
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
            ], ['COMMAND', 'PLAN'])
            self.log("============= LLM OUTPUT =============\n" + output['_output'], True)

            result_commands = output.get('COMMAND', [])
            if not result_commands:
                yield conversation.get_message("Not commands (1), early stop", role="assistant", message_type="error")
                break

            work_plan = output.get('PLAN', [])

            executed_commands_idx = {}
            for command in self.executed_commands:
                _key = command['opcode'] + ":" + json.dumps(command['arguments'])
                executed_commands_idx[_key] = True

            current_opcode = ''
            current_arguments = []
            for command in result_commands:
                opcode = parse_tags(command, ['OPCODE']).get('OPCODE', [''])[0]
                if not opcode:
                    continue

                arguments = parse_tags(command, ['ARG'], True).get('ARG', [''])
                _key = opcode + ":" + json.dumps(arguments)
                if opcode != 'RE_READ' and _key in executed_commands_idx:
                    continue

                current_opcode = opcode
                current_arguments = arguments
                if opcode not in ['EXIT', 'MESSAGE']:
                    log_str = f"Execute command: {opcode}; with argument: {arguments[0]}"
                    yield conversation.get_message(f"{log_str}", role="assistant", message_type="info")

                break

            if not current_opcode:
                yield conversation.get_message("Not commands (2), early stop", role="assistant", message_type="error")
                break

            result = self.interpreter.execute(current_opcode, current_arguments)
            self.executed_commands.append({
                'opcode': current_opcode,
                'arguments': current_arguments,
                'result': result.get('result', ''),
                'plan': work_plan,
            })
            self.log("============= EXECUTE =============\n" + "OPCODE=" + current_opcode + "\n\nARG=" + "\nARG=".join(current_arguments) + "\n\nRESULT=" + result.get('result', ''), True)

            is_inc_step = current_opcode not in ['MESSAGE']

            if result.get('exit', False):
                logger.info("Finished")
                break

            if result.get('output', False):
                yield conversation.get_message(result['result'], role="assistant", message_type="markdown")

            if is_inc_step:
                self.argent_step += 1

    def log(self, data, to_file=False):
        if type(data) is list or type(data) is dict:
            data = json.dumps(data, ensure_ascii=False, indent=4)

        if not to_file:
            logger.info(data)
            return

        with open('./conversations_log/log.log', "a", encoding='utf8') as f:
            f.write(data + "\n\n")

