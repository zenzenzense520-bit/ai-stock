"""国证历史调样文件的结构与异常测试。"""
from __future__ import annotations

import unittest
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from ai_stock.cni_audit import audit_periods, parse_adjustments


NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def workbook_bytes(rows: list[list[str]]) -> bytes:
    """构造最小官方同结构工作表，不依赖额外 Excel 包。"""
    root = ElementTree.Element(f"{{{NAMESPACE}}}worksheet")
    data = ElementTree.SubElement(root, f"{{{NAMESPACE}}}sheetData")
    for number, values in enumerate(rows, 1):
        row = ElementTree.SubElement(data, f"{{{NAMESPACE}}}row", r=str(number))
        for column, value in enumerate(values):
            cell = ElementTree.SubElement(
                row, f"{{{NAMESPACE}}}c", r=f"{chr(65 + column)}{number}")
            inner = ElementTree.SubElement(cell, f"{{{NAMESPACE}}}is")
            ElementTree.SubElement(inner, f"{{{NAMESPACE}}}t").text = value
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", ElementTree.tostring(root))
    return buffer.getvalue()


class CniAuditTest(unittest.TestCase):
    def test_parses_active_exits_and_candidates(self) -> None:
        # 修改说明：期次样本只由 OLD 和调入组成；调出、备选虽增加行数却不算样本。
        content = workbook_bytes([
            ["开始日期", "结束日期", "样本代码", "样本简称", "所属行业", "调整类型"],
            ["2024-06-17", "2024-12-13", "000001", "样本甲", "金融", "OLD"],
            ["2024-06-17", "2024-12-13", "000002", "样本乙", "工业", "+"],
            ["2024-06-17", "2024-12-13", "000003", "样本丙", "工业", "-"],
            ["2024-06-17", "2024-12-13", "000004", "样本丁", "工业", "备选"],
        ])
        members = parse_adjustments(content)
        self.assertEqual(len(members), 4)
        self.assertEqual(members[0].code, "000001")
        self.assertEqual(audit_periods(members, expected_size=2), [
            "2024-06-17: 4 行 / 2 个期次样本 (+=1, -=1, OLD=1, 备选=1) [OK]",
        ])
        self.assertIn("需核对", audit_periods(members, expected_size=3)[0])

    def test_flags_unbalanced_and_duplicate_entries(self) -> None:
        # 修改说明：缺少调出或重复期次样本均不得显示 OK。
        members = parse_adjustments(workbook_bytes([
            ["开始日期", "结束日期", "样本代码", "样本简称", "所属行业", "调整类型"],
            ["2024-06-17", "2024-12-13", "000001", "样本甲", "金融", "OLD"],
            ["2024-06-17", "2024-12-13", "000001", "样本甲", "金融", "+"],
        ]))
        self.assertIn("需核对", audit_periods(members, expected_size=2)[0])

    def test_rejects_non_xlsx_or_changed_header(self) -> None:
        with self.assertRaisesRegex(ValueError, "XLSX"):
            parse_adjustments(b"not a workbook")
        with self.assertRaisesRegex(ValueError, "表头"):
            parse_adjustments(workbook_bytes([["未知列"]]))
        with self.assertRaisesRegex(ValueError, "日期无效"):
            parse_adjustments(workbook_bytes([
                ["开始日期", "结束日期", "样本代码", "样本简称", "所属行业", "调整类型"],
                ["2024-13-17", "2024-12-13", "000001", "样本甲", "金融", "OLD"],
            ]))


if __name__ == "__main__":
    unittest.main()
