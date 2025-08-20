tools = [
    {
        "type":"function",
        "function":{
            "name": "read_file",
            "description": "Read file by path and return it content",
            "parameters": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "path to file"
                    }
                }
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name": "write_file",
            "description": "Write full data to file.\nUse this command ONLY if:\n1. You edit a file less than 100 lines\n2. You create new file.",
            "parameters": {
                "type": "object",
                "required": ["path", "content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "path to file"
                    },
                    "content": {
                        "type": "string",
                        "description":
"""data for write to the file, YOU MUST WRAP output ```, dont escape quotes (\") and brackets (< >)
example:
```json
{
    "id": 1
}```"""
                    }
                }
            }
        }
    },
{
        "type":"function",
        "function":{
            "name": "write_diff_file",
            "description": "Apply patch to existed file in the SEARCH/REPLACE format.\nUse this command ONLY if:\n1. file more than 100 lines\n2. you edit exists file\n",
            "parameters": {
                "type": "object",
                "required": ["path", "patch"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "path to file"
                    },
                    "patch": {
                        "type": "string",
                        "description":
"""patch for write to the file, SEARCH/REPLACE block, follow rules:
- block begins at:
<<<<<<< SEARCH
- next, print modified lines from source file, are will search and replace
- SEARCH-part MUST be small as possible and unique
- every line of source code begin with space char
- SEARCH-part CANT be empty
- next, print separator of SEARCH и REPLACE parts:
=======
- next, print lines for replacing, save all tab, spaces, comment, block comments etc
- SEARCH/REPLACE ends with:
>>>>>>> REPLACE
- if need to delete lines - REPLACE part MUST be empty
- save all tab, spaces, comment, block comments etc
- follow format considering for program language that you prints
- DONT put separator before `>>>>>>> REPLACE`
- put ALL changed into the ONCE COMMAND for current file.

Example:
<<<<<<< SEARCH
 from flask import Flask
=======
import math
from flask import Flask
>>>>>>> REPLACE

<<<<<<< SEARCH
 class Main:
   def method(self, a):
=======
class Main:
  def method(self, a: str):
>>>>>>> REPLACE"""
                    }
                }
            }
        }
    },
    {
        "type":"function",
        "function":{
            "name": "report",
            "description": "Print short report of you work.\nUse this command when you completely executed instructions and you have decided finish a work.",
            "parameters": {
                "type": "object",
                "required": ["text"],
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text is a report in the markdowm format. Dont write full content of files - short agenta is enough!"
                    }
                }
            }
        }
    },
]