import sys
import unittest
from pathlib import Path


SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER_DIR))

from routes.task_routes import map_task_for_client
from task_text_parser import parse_task_text


class TaskTextParserTests(unittest.TestCase):
    def test_acceptance_free_text_is_split_into_four_fields(self):
        text = (
            "15329199788"
            "贵州省黔西南州兴义市桔山街道大商汇b2组团3栋2单元2204"
            "杨仕现冰箱不制冷"
        )

        self.assertEqual(
            {
                "contact_phone": "15329199788",
                "detailed_address": "贵州省黔西南州兴义市桔山街道大商汇b2组团3栋2单元2204",
                "customer_name": "杨仕现",
                "fault_type": "冰箱不制冷",
            },
            parse_task_text(text),
        )

    def test_labeled_multiline_text_is_supported(self):
        parsed = parse_task_text(
            "联系人：杨仕现\n电话：15329199788\n"
            "地址：贵州省黔西南州兴义市桔山街道大商汇b2组团3栋2单元2204\n"
            "故障描述：冰箱不制冷"
        )

        self.assertEqual("杨仕现", parsed["customer_name"])
        self.assertEqual("15329199788", parsed["contact_phone"])
        self.assertEqual("冰箱不制冷", parsed["fault_type"])

    def test_mapping_adds_derived_fields_without_changing_dispatch_text(self):
        original = {
            "task_id": "task-1",
            "text": "杨仕现 15329199788 冰箱不制冷",
            "status": "draft",
        }

        mapped = map_task_for_client(original)

        self.assertEqual(original["text"], mapped["text"])
        self.assertEqual(original, {
            "task_id": "task-1",
            "text": "杨仕现 15329199788 冰箱不制冷",
            "status": "draft",
        })
        self.assertEqual("15329199788", mapped["parsed_fields"]["contact_phone"])


if __name__ == "__main__":
    unittest.main()
