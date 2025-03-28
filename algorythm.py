import json
import re
import os
import glob
import time
import datetime
from pathlib import Path

import conversation
from mcp_helper import tool_call
from llm_parser import parse_tags
from llm import llm_query

from dotenv import load_dotenv
load_dotenv()

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=os.getenv('MAX_ITERATION')

import logging
logger = logging.getLogger('APP')
logging.basicConfig(level=logging.INFO)

def _helper_get_relative_path(project_root: str, path: str) -> str:
    project_root = project_root.replace('\\', '/')
    path = path.replace('\\', '/')
    absolute_path = Path(project_root)
    return str(Path(path).relative_to(absolute_path)).replace('\\', '/')


def _helper_command_create_output(command: dict) -> str:
    arguments = command['arguments']
    result = command['result']
    opcode = command['opcode']

    arguments_str = "    \n".join([f"<ARG>{arg}</ARG>" for arg in arguments])

    return f"""<COMMAND>
    <OPCODE>{opcode}</OPCODE>
{arguments_str}
    <RESULT>{result}</RESULT>
</COMMAND>"""


class CommandInterpreter:
    def __init__(self, mcp_host):
        self.mcp_host = mcp_host

    def _command_read(self, file_path) -> dict:
        content = tool_call(self.mcp_host, 'get_file_text_by_path', {
            'pathInProject': file_path,
        })
        return {'result': content.get('status', 'False'), 'exists': 'status' in content}

    def _command_list(self, path) -> dict:
        content = tool_call(self.mcp_host, 'list_files_in_folder', {
            'pathInProject': path,
        })

        if 'error' in content:
            return {'result': "ERROR: Path not exists"}

        result = []

        content['status'] = content['status'].replace('\\', '/').replace('//', '/')
        try:
            content = json.loads(content['status'])
        except:
            logger.error("JSON decode: " + content['status'])
            raise Exception("JSON decode")

        for obj in content:
            _path = obj['path'].replace('\\', '/')
            if obj['type'] == 'directory':
                _path += '/'
            result.append(f"- {_path}")

        return {'result': "\n".join(result)}

    def _command_write(self, file_path, data) -> dict:
        # looking for file exists:
        is_exist = self._command_read(file_path)['exists']
        if is_exist:
            method = 'replace_file_text_by_path'
        else:
            method = 'create_new_file_with_text'

        content = tool_call(self.mcp_host, method, {
            'pathInProject': file_path,
            'text': data,
        })

        return {'result': "True" if 'status' in content else "ERROR: " + content['error']}

    def _command_message(self, data) -> dict:
        return {'result': data, 'output': True}

    def execute(self, opcode: str, arguments) -> dict:
        if opcode == 'READ':
            return self._command_read(*arguments)
        elif opcode == 'LIST':
            return self._command_list(*arguments)
        elif opcode == 'WRITE':
            return self._command_write(*arguments)
        elif opcode == 'EXIT':
            return {'exit': True}
        elif opcode == 'MESSAGE':
            return self._command_message(*arguments)
        else:
            raise Exception(f"Unknown opcode: {opcode}")


class Copilot:
    PROJECT_DESCRIPTION = "./.copilot_project.xml"
    STEP_TOOL_READ_MANIFEST = 'tooluse_read_project_config'
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

    def _run_llm_iteration(self) -> bool:
        if self.argent_step >= self.MAX_STEP:
            logger.warning("MAX_STEP exceed!")
            self.output = [conversation.get_message("```MAX_STEP exceed!```\n\n", role="assistant")]
            return False

        current_open_file = ''
        if self.manifest['current_open_file']:
            current_open_file = f"Path of current open file in IDE: `{self.manifest['current_open_file']}`"

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
        ], ['COMMAND'])
        self.log("============= LLM OUTPUT =============\n" + output['_output'], True)

        result_commands = output.get('COMMAND', [])
        if not result_commands:
            self.output = [conversation.get_message("```Not commands (1), early stop```\n\n", role="assistant")]
            return False

        executed_commands_idx = {}
        for command in self.executed_commands:
            _key = command['opcode'] + ":" + ":" + json.dumps(command['arguments'])
            executed_commands_idx[_key] = True

        result = {}
        for command in result_commands:
            opcode = parse_tags(command, ['OPCODE']).get('OPCODE', ['empty'])[0]
            if opcode == 'empty':
                continue

            arguments = parse_tags(command, ['ARG'], True).get('ARG', [''])
            _key = opcode + ":" + ":" + json.dumps(arguments)
            if _key in executed_commands_idx:
                continue

            if opcode not in ['EXIT', 'MESSAGE']:
                log_str = f"Execute command: {opcode}; with argument: {arguments[0]}"
                self.output.append(
                    conversation.get_message(f"```bash\n{log_str}\n``` \n",
                                               role="assistant")
                )

            result = self.interpreter.execute(opcode, arguments)
            self.executed_commands.append({
                'opcode': opcode,
                'arguments': arguments,
                'result': result.get('result', ''),
            })

            break

        if not result:
            self.output = [conversation.get_message("Not commands (2), early stop\n\n", role="assistant")]
            return False

        if result.get('exit', False):
            logger.info("Finished")
            return False

        if result.get('output', False):
            self.output.append(conversation.get_message(result['result'] + " \n\n", role="assistant"))


        self.argent_step += 1
        return True

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

        # first copilot's message contains conversation's id
        for messages in self.request['messages']:
            if messages['role'] == 'assistant':
                _id = re.findall(r'^```<CONSERVATION_ID>(\d+\.\d+)</CONSERVATION_ID>```', messages['content'])
                assert _id[0], 'Empty conversation_id'
                self.conversation_id = _id[0]
                break

        if self.conversation_id:
            return

        self.conversation_id = time.time()

        _manifest_file = tool_call(IDE_MCP_HOST, 'get_file_text_by_path', {'pathInProject': './.copilot_project.xml'})[
            'status']
        manifest = parse_tags(_manifest_file, ['path', 'description', 'mcp'])

        _project_base_path = manifest['path'][0].strip()
        _current_open_file = tool_call(IDE_MCP_HOST, 'get_open_in_editor_file_path')['status']
        if _current_open_file:
            _current_open_file = _helper_get_relative_path(_project_base_path, _current_open_file)

        self.manifest = {
            'base_path': _project_base_path,
            'description': manifest['description'][0].strip(),
            'files_structure': self._read_project_structure(_project_base_path),
            'current_open_file': _current_open_file,
        }

        self.output = [
            conversation.get_message(f"```<CONSERVATION_ID>{self.conversation_id}</CONSERVATION_ID>```\n\n", "assistant"),
            # conversation.get_message(f"```JSON\n{json.dumps(self.manifest, ensure_ascii=False, indent=4)}\n```\n\n",
            #                          "assistant"),
        ]

        self.executed_commands = []
        self.argent_step = 1
        self.interpreter = CommandInterpreter(IDE_MCP_HOST)

    def _read_project_structure(self, base_path) -> list:
        result = []
        for dir_object in glob.glob(base_path + "/*"):
            is_dir = os.path.isdir(dir_object)

            dir_object = _helper_get_relative_path(base_path, dir_object)

            if is_dir:
                dir_object = dir_object + "/"

            result.append(dir_object)
        return result

    def run(self):
        logger.info("RUN. Messages:")
        logger.info(self.request['messages'])
        with open('./conversations_log/log.log', "w", encoding='utf8') as f:
            f.write(str(datetime.datetime.now()) + "\n\n")

        while True:
            self.output = []
            self._init()

            result = self._run_llm_iteration()
            yield from self.output

            if not result:
                self.log("run(): finished")
                yield conversation.get_terminal()
                return

            self.log("run(): next step")


        #logger.info(f"ID: {self.conversation_id}; STEP: {self.last_step}")
        # logger.info("MANIFEST:")
        # logger.info(self.manifest)

    def log(self, data, to_file=False):
        if type(data) is list or type(data) is dict:
            data = json.dumps(data, ensure_ascii=False, indent=4)

        if not to_file:
            logger.info(data)
            return

        with open('./conversations_log/log.log', "a", encoding='utf8') as f:
            f.write(data + "\n\n")

