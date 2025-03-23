output = """I'll help create a file with user data example. Let's start by creating a JSON file with sample user data.

<COMMAND>
    <OPCODE>WRITE</OPCODE>
    <ARG name="path">fixtures/users.json</ARG>
    <ARG name="data">{
    "users": [
        {
            "id": 1,
            "username": "john_doe",
            "email": "john.doe@example.com",
            "full_name": "John Doe",
            "age": 30,
            "is_active": true,
            "created_at": "2024-01-15T10:00:00Z",
            "roles": ["user", "admin"],
            "settings": {
                "notifications": true,
                "language": "en",
                "theme": "dark"
            }
        },
        {
            "id": 2,
            "username": "jane_smith",
            "email": "jane.smith@example.com",
            "full_name": "Jane Smith",
            "age": 25,
            "is_active": true,
            "created_at": "2024-01-16T15:30:00Z",
            "roles": ["user"],
            "settings": {
                "notifications": false,
                "language": "es",
                "theme": "light"
            }
        }
    ]
}</ARG>
</COMMAND>"""

from llm_parser import parse_tags

print(parse_tags(output, ['COMMAND']))