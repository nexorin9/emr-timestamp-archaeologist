"""
EMR Timestamp Archaeologist - 解析器单元测试
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from models import EmrTimestampRecord
from parser import (
    CsvParser,
    JsonParseError,
    CsvParseError,
    JsonParser,
    normalize_timestamp,
    parse_directory,
    parse_file,
    ParserFactory,
    ParserError,
    XmlParser,
    XmlParseError,
)


class TestNormalizeTimestamp:
    """测试时间戳标准化函数"""

    def test_none_input(self):
        """None 输入返回 None"""
        assert normalize_timestamp(None) is None

    def test_empty_string(self):
        """空字符串返回 None"""
        assert normalize_timestamp("") is None
        assert normalize_timestamp("   ") is None

    def test_datetime_input(self):
        """datetime 对象直接返回"""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        assert normalize_timestamp(dt) == dt

    def test_standard_format(self):
        """标准格式 %Y-%m-%d %H:%M:%S"""
        result = normalize_timestamp("2024-01-15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_iso8601_format(self):
        """ISO8601 格式"""
        result = normalize_timestamp("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_iso8601_with_milliseconds(self):
        """带毫秒的 ISO8601"""
        result = normalize_timestamp("2024-01-15T10:30:00.123")
        assert result == datetime(2024, 1, 15, 10, 30, 0, 123000)

    def test_chinese_format(self):
        """中文日期格式"""
        result = normalize_timestamp("2024/01/15 10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_date_only(self):
        """仅日期格式"""
        result = normalize_timestamp("2024-01-15")
        assert result == datetime(2024, 1, 15, 0, 0, 0)

    def test_unix_timestamp_seconds(self):
        """Unix 时间戳（秒）"""
        # 1705315800 = 2024-01-15 18:50:00 UTC
        result = normalize_timestamp(1705315800)
        assert result is not None
        assert isinstance(result, datetime)
        # 验证是合理的时间戳（2024年）
        assert 2024 <= result.year <= 2025

    def test_unix_timestamp_milliseconds(self):
        """Unix 时间戳（毫秒）"""
        # 1705315800123 = 2024-01-15 18:50:00.123 UTC
        result = normalize_timestamp(1705315800123)
        assert result is not None
        assert isinstance(result, datetime)
        # 验证毫秒部分
        assert result.microsecond >= 100000  # 至少有100ms
        assert 2024 <= result.year <= 2025

    def test_invalid_format(self):
        """无效格式返回 None"""
        assert normalize_timestamp("not a date") is None
        assert normalize_timestamp("2024-13-45") is None


class TestXmlParser:
    """测试 XML 解析器"""

    def test_parse_simple_xml(self, tmp_path):
        """解析简单 XML 文件"""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <records>
            <record>
                <patient_id>P001</patient_id>
                <visit_id>V001</visit_id>
                <record_id>R001</record_id>
                <record_type>入院记录</record_type>
                <business_time>2024-01-15 08:00:00</business_time>
                <chapter>
                    <chapter_id>ch1</chapter_id>
                    <chapter_name>主诉</chapter_name>
                    <created_time>2024-01-15 08:05:00</created_time>
                    <modified_time>2024-01-15 08:05:00</modified_time>
                    <author_id>DR001</author_id>
                </chapter>
                <chapter>
                    <chapter_id>ch2</chapter_id>
                    <chapter_name>现病史</chapter_name>
                    <created_time>2024-01-15 08:10:00</created_time>
                    <modified_time>2024-01-15 08:10:00</modified_time>
                    <author_id>DR001</author_id>
                </chapter>
            </record>
        </records>
        """
        file_path = tmp_path / "test.xml"
        file_path.write_text(xml_content, encoding="utf-8")

        records = parse_file(file_path)
        assert len(records) == 1
        assert records[0].patient_id == "P001"
        assert records[0].visit_id == "V001"
        assert records[0].record_type == "入院记录"
        assert len(records[0].chapters) == 2
        assert records[0].chapters[0].chapter_name == "主诉"
        assert records[0].chapters[1].chapter_name == "现病史"

    def test_parse_xml_file_not_found(self):
        """文件不存在时抛出异常"""
        with pytest.raises(ParserError):
            parse_file("nonexistent.xml")

    def test_parse_invalid_xml(self, tmp_path):
        """无效 XML 抛出异常"""
        file_path = tmp_path / "invalid.xml"
        file_path.write_text("<not valid xml", encoding="utf-8")

        with pytest.raises(XmlParseError):
            parse_file(file_path)

    def test_xml_multiple_records(self, tmp_path):
        """解析多条记录"""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
        <records>
            <record>
                <patient_id>P001</patient_id>
                <visit_id>V001</visit_id>
                <record_id>R001</record_id>
                <record_type>入院记录</record_type>
                <chapter>
                    <chapter_id>ch1</chapter_id>
                    <chapter_name>主诉</chapter_name>
                    <created_time>2024-01-15 08:05:00</created_time>
                    <author_id>DR001</author_id>
                </chapter>
            </record>
            <record>
                <patient_id>P002</patient_id>
                <visit_id>V002</visit_id>
                <record_id>R002</record_id>
                <record_type>出院记录</record_type>
                <chapter>
                    <chapter_id>ch1</chapter_id>
                    <chapter_name>出院小结</chapter_name>
                    <created_time>2024-01-20 10:00:00</created_time>
                    <author_id>DR002</author_id>
                </chapter>
            </record>
        </records>
        """
        file_path = tmp_path / "multi.xml"
        file_path.write_text(xml_content, encoding="utf-8")

        records = parse_file(file_path)
        assert len(records) == 2
        assert records[0].patient_id == "P001"
        assert records[1].patient_id == "P002"


class TestJsonParser:
    """测试 JSON 解析器"""

    def test_parse_simple_json(self, tmp_path):
        """解析简单 JSON 文件"""
        json_content = {
            "records": [
                {
                    "patient_id": "P001",
                    "visit_id": "V001",
                    "record_id": "R001",
                    "record_type": "入院记录",
                    "business_time": "2024-01-15 08:00:00",
                    "chapters": [
                        {
                            "chapter_id": "ch1",
                            "chapter_name": "主诉",
                            "created_time": "2024-01-15 08:05:00",
                            "author_id": "DR001"
                        },
                        {
                            "chapter_id": "ch2",
                            "chapter_name": "现病史",
                            "created_time": "2024-01-15 08:10:00",
                            "author_id": "DR001"
                        }
                    ]
                }
            ]
        }
        file_path = tmp_path / "test.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json_content, f)

        records = parse_file(file_path)
        assert len(records) == 1
        assert records[0].patient_id == "P001"
        assert records[0].record_type == "入院记录"
        assert len(records[0].chapters) == 2

    def test_parse_json_camel_case(self, tmp_path):
        """解析驼峰命名 JSON"""
        json_content = {
            "records": [
                {
                    "patientId": "P001",
                    "visitId": "V001",
                    "recordId": "R001",
                    "recordType": "入院记录",
                    "chapters": [
                        {
                            "chapterId": "ch1",
                            "chapterName": "主诉",
                            "createdTime": "2024-01-15 08:05:00",
                            "authorId": "DR001"
                        }
                    ]
                }
            ]
        }
        file_path = tmp_path / "camel.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(json_content, f)

        records = parse_file(file_path)
        assert len(records) == 1
        assert records[0].patient_id == "P001"

    def test_parse_invalid_json(self, tmp_path):
        """无效 JSON 抛出异常"""
        file_path = tmp_path / "invalid.json"
        file_path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises(JsonParseError):
            parse_file(file_path)

    def test_parse_json_file_not_found(self):
        """文件不存在时抛出异常"""
        with pytest.raises(ParserError):
            parse_file("nonexistent.json")


class TestCsvParser:
    """测试 CSV 解析器"""

    def test_parse_simple_csv(self, tmp_path):
        """解析简单 CSV 文件"""
        csv_content = """patient_id,visit_id,record_id,record_type,chapter_id,chapter_name,created_time,author_id
P001,V001,R001,入院记录,ch1,主诉,2024-01-15 08:05:00,DR001
P001,V001,R001,入院记录,ch2,现病史,2024-01-15 08:10:00,DR001
P002,V002,R002,出院记录,ch1,出院小结,2024-01-20 10:00:00,DR002"""
        file_path = tmp_path / "test.csv"
        file_path.write_text(csv_content, encoding="utf-8")

        records = parse_file(file_path)
        assert len(records) == 2

        # 检查第一条记录
        record1 = next(r for r in records if r.patient_id == "P001")
        assert record1.visit_id == "V001"
        assert len(record1.chapters) == 2

        # 检查第二条记录
        record2 = next(r for r in records if r.patient_id == "P002")
        assert record2.record_type == "出院记录"

    def test_parse_empty_csv(self, tmp_path):
        """空 CSV 抛出异常"""
        file_path = tmp_path / "empty.csv"
        file_path.write_text("", encoding="utf-8")

        with pytest.raises(CsvParseError):
            parse_file(file_path)


class TestParserFactory:
    """测试解析器工厂"""

    def test_get_xml_parser(self):
        """获取 XML 解析器"""
        parser = ParserFactory.get_parser("test.xml")
        assert isinstance(parser, XmlParser)

    def test_get_json_parser(self):
        """获取 JSON 解析器"""
        parser = ParserFactory.get_parser("test.json")
        assert isinstance(parser, JsonParser)

    def test_get_csv_parser(self):
        """获取 CSV 解析器"""
        parser = ParserFactory.get_parser("test.csv")
        assert isinstance(parser, CsvParser)

    def test_unsupported_extension(self):
        """不支持的扩展名抛出异常"""
        with pytest.raises(ValueError) as exc_info:
            ParserFactory.get_parser("test.txt")
        assert "不支持的文件格式" in str(exc_info.value)


class TestParseDirectory:
    """测试目录解析"""

    def test_parse_directory(self, tmp_path):
        """批量解析目录下文件"""
        # 创建 XML 文件
        xml_content = """<?xml version="1.0"?>
        <records>
            <record>
                <patient_id>P001</patient_id>
                <visit_id>V001</visit_id>
                <record_id>R001</record_id>
                <record_type>入院记录</record_type>
                <chapter>
                    <chapter_id>ch1</chapter_id>
                    <chapter_name>主诉</chapter_name>
                    <created_time>2024-01-15 08:05:00</created_time>
                    <author_id>DR001</author_id>
                </chapter>
            </record>
        </records>
        """
        (tmp_path / "test1.xml").write_text(xml_content, encoding="utf-8")

        # 创建 JSON 文件
        json_content = {
            "records": [{
                "patient_id": "P002",
                "visit_id": "V002",
                "record_id": "R002",
                "record_type": "出院记录",
                "chapters": [{
                    "chapter_id": "ch1",
                    "chapter_name": "出院小结",
                    "created_time": "2024-01-20 10:00:00",
                    "author_id": "DR002"
                }]
            }]
        }
        with open(tmp_path / "test2.json", "w", encoding="utf-8") as f:
            json.dump(json_content, f)

        records = parse_directory(tmp_path)
        assert len(records) == 2

    def test_parse_directory_with_extension_filter(self, tmp_path):
        """指定扩展名过滤"""
        xml_content = """<?xml version="1.0"?><records><record>
            <patient_id>P001</patient_id>
            <visit_id>V001</visit_id>
            <record_id>R001</record_id>
            <record_type>入院记录</record_type>
            <chapter>
                <chapter_id>ch1</chapter_id>
                <chapter_name>主诉</chapter_name>
                <created_time>2024-01-15 08:05:00</created_time>
                <author_id>DR001</author_id>
            </chapter>
        </record></records>"""
        (tmp_path / "test.xml").write_text(xml_content, encoding="utf-8")

        json_content = {"records": []}
        with open(tmp_path / "test.json", "w", encoding="utf-8") as f:
            json.dump(json_content, f)

        # 只解析 XML
        records = parse_directory(tmp_path, extensions=[".xml"])
        assert len(records) == 1

    def test_parse_nonexistent_directory(self):
        """不存在的目录抛出异常"""
        with pytest.raises(ParserError) as exc_info:
            parse_directory("nonexistent_dir")
        assert "目录不存在" in str(exc_info.value)


class TestParseFile:
    """测试文件解析主入口"""

    def test_parse_xml_by_extension(self, tmp_path):
        """根据扩展名自动选择解析器"""
        xml_content = """<?xml version="1.0"?>
        <records>
            <record>
                <patient_id>P001</patient_id>
                <visit_id>V001</visit_id>
                <record_id>R001</record_id>
                <record_type>入院记录</record_type>
                <chapter>
                    <chapter_id>ch1</chapter_id>
                    <chapter_name>主诉</chapter_name>
                    <created_time>2024-01-15 08:05:00</created_time>
                    <author_id>DR001</author_id>
                </chapter>
            </record>
        </records>
        """
        file_path = tmp_path / "auto.xml"
        file_path.write_text(xml_content, encoding="utf-8")

        records = parse_file(file_path)
        assert len(records) == 1
        assert isinstance(records[0], EmrTimestampRecord)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])