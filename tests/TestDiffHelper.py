import unittest
import json
from itertools import count

from diff_helper import apply_patch

class TestDiffHelper(unittest.TestCase):
    CODE_JSON = """[
    {
        "name": "John Smith",
        "date_of_birth": "1985-03-15",
        "sex": "M",
        "phone": "+1-555-0101"
    },
    {
        "name": "Emma Wilson",
        "date_of_birth": "1990-07-22",
        "sex": "F",
        "phone": "+1-555-0102"
    },
    {
        "name": "Michael Brown",
        "date_of_birth": "1988-11-30",
        "sex": "M",
        "phone": "+1-555-0103"
    }
]"""

    def test_1(self):
        PATCH = """<<<<<<< SEARCH
    {
        "name": "John Smith",
        "date_of_birth": "1985-03-15",
        "sex": "M",
        "phone": "+1-555-0101"
    },
=======
    {
        "name": "John Smith",
        "date_of_birth": "1985-03-15",
        "sex": "M",
        "phone": "+1-555-0101",
        "region_id": 1
    },
>>>>>>> REPLACE

<<<<<<< SEARCH
    {
        "name": "Emma Wilson",
        "date_of_birth": "1990-07-22",
        "sex": "F",
        "phone": "+1-555-0102"
    },
=======
    {
        "name": "Emma Wilson",
        "date_of_birth": "1990-07-22",
        "sex": "F",
        "phone": "+1-555-0102",
        "region_id": 2
    },
>>>>>>> REPLACE

<<<<<<< SEARCH
    {
        "name": "Michael Brown",
        "date_of_birth": "1988-11-30",
        "sex": "M",
        "phone": "+1-555-0103"
    }
=======
    {
        "name": "Michael Brown",
        "date_of_birth": "1988-11-30",
        "sex": "M",
        "phone": "+1-555-0103",
        "region_id": 3
    }
>>>>>>> REPLACE"""

        patched = apply_patch(self.CODE_JSON, PATCH)
        patched_obj = json.loads(patched)

        self.assertEqual(23, len(patched.split("\n")))

        self.assertEqual({
            "name": "John Smith",
            "date_of_birth": "1985-03-15",
            "sex": "M",
            "phone": "+1-555-0101",
            "region_id": 1
        }, patched_obj[0])

        self.assertEqual({
            "name": "Emma Wilson",
            "date_of_birth": "1990-07-22",
            "sex": "F",
            "phone": "+1-555-0102",
            "region_id": 2
        }, patched_obj[1])

        self.assertEqual({
            "name": "Michael Brown",
            "date_of_birth": "1988-11-30",
            "sex": "M",
            "phone": "+1-555-0103",
            "region_id": 3
        }, patched_obj[2])

    def test_2(self):
        PATCH = """<<<<<<< SEARCH
    {
        "name": "John Smith",
        "date_of_birth": "1985-03-15",
        "sex": "M",
        "phone": "+1-555-0101"
    },
=======
>>>>>>> REPLACE

<<<<<<< SEARCH
    {
        "name": "Emma Wilson",
        "date_of_birth": "1990-07-22",
        "sex": "F",
        "phone": "+1-555-0102"
    },
=======
    {
        "name": "Emma Wilson",
        "date_of_birth": "1990-07-22",
        "sex": "F",
        "phone": "+1-555-0102",
        "region_id": 2,
        "region_code": "EN"
    },
>>>>>>> REPLACE"""

        patched = apply_patch(self.CODE_JSON, PATCH)
        patched_obj = json.loads(patched)

        self.assertEqual(16, len(patched.split("\n")))
        self.assertEqual(2, len(patched_obj))

        self.assertEqual({
            "name": "Emma Wilson",
            "date_of_birth": "1990-07-22",
            "sex": "F",
            "phone": "+1-555-0102",
            "region_id": 2,
            "region_code": "EN",
        }, patched_obj[0])

        self.assertEqual({
            "name": "Michael Brown",
            "date_of_birth": "1988-11-30",
            "sex": "M",
            "phone": "+1-555-0103"
        }, patched_obj[1])