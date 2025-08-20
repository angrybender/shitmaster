import os
import json

import logging
logger = logging.getLogger('APP')

from dotenv import load_dotenv
load_dotenv()

from llm import llm_query
from command_interpreter import CommandInterpreter
from prompts.analytic_tools import tools as analytic_tools
from prompts.coder_tools import tools as coder_tools

IDE_MCP_HOST=os.getenv('IDE_MCP_HOST')
MAX_ITERATION=int(os.getenv('MAX_ITERATION'))

class BaseAgent:
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

    def get_tools(self) -> list[dict]:
        return []

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
        sub_prompt = self.step_prompt.format(
            project_description=self.project_description,
            current_file_open=current_open_file,
            project_structure="\n".join([f"- {path}" for path in self.project_structure]),
        )

        self.log("============= INSTRUCTION =============\n" + self.instruction, True)

        conversation = [
            {
                'role': 'system',
                'content': self.system_prompt + "\n" + sub_prompt
            },
            {
                'role': 'user',
                'content': self.instruction
            }
        ]

        agent_step = 1
        while True:
            if agent_step > MAX_ITERATION:
                logger.warning("MAX_STEP exceed!")
                yield {
                    'message': "MAX_STEP exceed!",
                    'type': "error",
                    'exit': True,
                }
                break

            output = llm_query(conversation, tools=self.get_tools())
            self.log("============= LLM OUTPUT =============", True)

            tool_call_description = None
            current_tool_call = None
            for tool_call in output['_tool_calls']:
                tool_call_description = {
                    'function': tool_call.function.name,
                    'id': tool_call.id,
                    'args': list(json.loads(tool_call.function.arguments).values())
                }
                current_tool_call = tool_call
                break

            if not current_tool_call:
                yield {
                    'message': "Not commands (1), early stop",
                    'type': "error",
                    'exit': True,
                }
                break

            self.log(tool_call_description, True)
            conversation.append({
                'role': 'assistant',
                'content': output['_output'],
                'tool_calls': [current_tool_call]
            })

            if tool_call_description['function'] == 'report':
                yield {
                    'message': tool_call_description['args'][0],
                    'type': "report",
                    'exit': True,
                }
                break
            else:
                yield {
                    'message': f"Execute command: {tool_call_description['function']}; with argument: {tool_call_description['args'][0]}",
                    'type': "info",
                    'exit': False,
                }
                result = self.interpreter.execute(tool_call_description['function'], tool_call_description['args'])
                result_msg = {
                    'role': 'tool',
                    'tool_call_id': current_tool_call.id,
                    'name': current_tool_call.function.name,
                    'content': result['result'],
                }
                self.log("TOOL RESULT:", True)
                self.log(result_msg, True)

                conversation.append(result_msg)

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


class AnalyticAgent(BaseAgent):
    def get_tools(self) -> list[dict]:
        return analytic_tools

class CoderAgent(BaseAgent):
    def get_tools(self) -> list[dict]:
        return coder_tools


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

        if role == 'ANALYTIC':
            return AnalyticAgent(role, system_prompt, step_prompt)
        elif role == 'CODER':
            return CoderAgent(role, system_prompt, step_prompt)




