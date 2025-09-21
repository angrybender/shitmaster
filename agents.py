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

def _parse_tool_arguments(json_data: str):
    try:
        return json.loads(json_data)
    except json.decoder.JSONDecodeError as e:
        json_data = llm_query(f"fix this JSON: ```{json_data}```\nwrap answer into tag <RESULT>", ['RESULT']).get('RESULT', [''])[0]
        if not json_data:
            raise e

        return json.loads(json_data)


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
        self.thinking = False

    def conversation_filter(self, conversation: list[dict]) -> list[dict]:
        return conversation

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
        max_skip_command = 3
        while True:
            if agent_step > MAX_ITERATION:
                logger.warning("MAX_STEP exceed!")
                yield {
                    'message': "MAX_STEP exceed!",
                    'type': "error",
                    'exit': True,
                }
                break

            conversation = self.conversation_filter(conversation)

            if self.thinking:
                think_output = llm_query(conversation)
                think_output = think_output.get('_output', '')
                if think_output and think_output.find('<work_plan>') > -1:
                    think_output_msg = think_output\
                                            .replace('<work_plan>', '')\
                                            .replace('</work_plan>', '')
                    yield {
                        'message': think_output_msg,
                        'type': "markdown",
                    }

                    conversation.append({
                        'role': 'assistant',
                        'content': think_output
                    })

            output = llm_query(conversation, tools=self.get_tools())
            self.log("============= LLM OUTPUT =============", True)
            self.log('LLM OUTPUT:\n' + output.get('output', ''), True)

            tool_call_description = None
            current_tool_call = None
            tool_calls = output.get('_tool_calls', [])
            if not tool_calls:
                tool_calls = []

            for tool_call in tool_calls:
                tool_call_description = {
                    'function': tool_call.function.name,
                    'id': tool_call.id,
                    'args': list(_parse_tool_arguments(tool_call.function.arguments).values()) if tool_call.function.arguments else []
                }
                current_tool_call = tool_call
                break

            if not current_tool_call and (max_skip_command <= 0 or not output['_output']):
                yield {
                    'message': "Not commands (1), early stop",
                    'type': "error",
                    'exit': True,
                }
                break
            elif not current_tool_call and output['_output']:
                max_skip_command -= 1

                yield {
                    'message': output['_output'],
                    'type': "markdown",
                    'exit': True,
                }

                conversation.append({
                    'role': 'assistant',
                    'content': output['_output'],
                })

                continue

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
                    'message': f"🔨 {tool_call_description['function']}: {tool_call_description['args'][0]}",
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
    def __init__(self, role: str, system_prompt: str, step_prompt: str):
        super().__init__(role, system_prompt, step_prompt)
        self.thinking = True

    def get_tools(self) -> list[dict]:
        return analytic_tools

class CoderAgent(BaseAgent):
    def get_tools(self) -> list[dict]:
        return coder_tools

    def conversation_filter(self, conversation: list[dict]) -> list[dict]:
        last_tool = ''
        modified_conversation = []
        for m in conversation:
            modified_conversation.append(m)

            if 'tool_calls' not in m:
                continue

            tool = m['tool_calls'][0]
            _hash = tool.function.name + ':' + tool.function.arguments

            if tool.function.name != 'read_file':
                last_tool = _hash
                continue

            if _hash == last_tool:
                modified_conversation.append({
                    'role': 'tool',
                    'tool_call_id': tool.id,
                    'name': tool.function.name,
                    'content': 'File has read above!',
                })

                return modified_conversation
            else:
                last_tool = _hash

        return conversation


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




