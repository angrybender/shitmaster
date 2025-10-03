import unittest
import os

from command_interpreter import CommandInterpreter

class TestCommandInterpreter(unittest.TestCase):
    def test_command_list1(self):
        root_path = os.path.join(os.path.dirname(__file__), '..')
        instance = CommandInterpreter('', str(root_path))
        result = instance.execute('list_in_directory', ['.'])

        result = result['result'] + '\n'
        self.assertIn('- .env\n', result, 'file check')
        self.assertIn('- tests/\n', result, 'dir check')

    def test_command_list2(self):
        root_path = os.path.join(os.path.dirname(__file__), '..', '_invalid_dir')
        instance = CommandInterpreter('', str(root_path))
        result = instance.execute('list_in_directory', ['.'])

        self.assertIn('ERROR:', result['result'])