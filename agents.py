import os
import json

import logging
logger = logging.getLogger('APP')

from dotenv import load_dotenv
load_dotenv()

from llm import llm_query
from command_interpreter import CommandInterpreter
from llm_parser import parse_tags

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=int(os.getenv('MAX_ITERATION'))


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

class BaseAgent:
    ROLES = ["ANALYTIC", "CODER", "SUPERVISOR"]

    def __init__(self, role: str, system_prompt: str, step_prompt: str):
        self.system_prompt = system_prompt
        self.step_prompt = step_prompt

        self.instruction = None
        self.project_description = None
        self.project_structure = None
        self.current_open_file = None
        self.interpreter = None
        self.role = role
        self.log_file = role

    def init(self, instruction: str, manifest: dict, log_file: str):
        self.instruction = instruction
        self.project_description = manifest['description']
        self.project_structure = manifest['files_structure']
        self.current_open_file = manifest['current_open_file']
        self.interpreter = CommandInterpreter(IDE_MCP_HOST)
        self.log_file = log_file

    def run(self):
        assert self.instruction, 'Init() s required'
        executed_commands = []

        yield {
            'message': f"start {self.role}...",
            'type': "info",
        }

        current_open_file = ''
        if self.current_open_file:
            current_open_file = f"Path of current open file in IDE: `{self.current_open_file}`"

        agent_step = 1
        prompt_appendix = ''
        while True:
            if agent_step > MAX_ITERATION:
                logger.warning("MAX_STEP exceed!")
                yield {
                    'message': "MAX_STEP exceed!",
                    'type': "error",
                    'exit': True,
                }
                break

            current_prompt = self.step_prompt.format(
                project_description=self.project_description,
                current_file_open=current_open_file,
                project_structure="\n".join([f"- {path}" for path in self.project_structure]),
                instruction=self.instruction + prompt_appendix,
                commands_prev_step="\n".join(
                    [_helper_command_create_output(_) for _ in executed_commands]
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
                yield {
                    'message': "Not commands (1), early stop",
                    'type': "error",
                    'exit': True,
                }
                break

            work_plan = output.get('PLAN', [])

            executed_commands_idx = {}
            for command in executed_commands:
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
                if opcode not in ['REPORT']:
                    log_str = f"Execute command: {opcode}; with argument: {arguments[0]}"
                    yield {
                        'message': f"{log_str}",
                        'type': "info",
                        'exit': False,
                    }

                break

            if not current_opcode and not prompt_appendix:
                prompt_appendix = '\nWrite detailed report of you work based on <COMMANDS> data!'
                yield {
                    'message': "Early exit",
                    'type': "info",
                    'exit': True,
                }
                continue

            if not current_opcode and prompt_appendix:
                yield {
                    'message': "Not commands (2), early stop",
                    'type': "error",
                    'exit': True,
                }
                break

            if current_opcode != 'REPORT':
                result = self.interpreter.execute(current_opcode, current_arguments)
            else:
                yield {
                    'message': current_arguments[0],
                    'type': "report",
                    'exit': True,
                }
                break

            executed_commands.append({
                'opcode': current_opcode,
                'arguments': current_arguments,
                'result': result.get('result', ''),
                'plan': work_plan,
            })
            self.log("============= EXECUTE =============\n" + "OPCODE=" + current_opcode + "\n\nARG=" + "\nARG=".join(
                current_arguments) + "\n\nRESULT=" + result.get('result', ''), True)

            if result.get('exit', False):
                logger.info("Finished")
                break

            if result.get('output', False):
                yield {
                    'message': result['result'],
                    'type': "markdown",
                    'exit': False,
                }

            agent_step += 1

    def log(self, data, to_file=False):
        if type(data) is list or type(data) is dict:
            data = json.dumps(data, ensure_ascii=False, indent=4)

        data = f"[ {self.role} ] {data}"

        if not to_file:
            logger.info(data)
            return

        with open(self.log_file, "a", encoding='utf8') as f:
            f.write(data + "\n\n")


class Agent:
    PROMPTS = {
        'ANALYTIC': './prompts/analytic_system.txt',
        'CODER': './prompts/coder_system.txt',
    }

    STEP_PROMPT = './prompts/step.txt'

    @staticmethod
    def fabric(role) -> BaseAgent:
        assert role in Agent.PROMPTS, f'invalid role: {role}'

        system_prompt = Agent.PROMPTS[role]
        with open(system_prompt, 'r', encoding='utf8') as f:
            system_prompt = f.read()

        with open(Agent.STEP_PROMPT, 'r', encoding='utf8') as f:
            step_prompt = f.read()

        return BaseAgent(role, system_prompt, step_prompt)



