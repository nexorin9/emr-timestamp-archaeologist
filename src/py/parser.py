"""
EMR Timestamp Archaeologist - EMR 元数据解析器
支持 XML、JSON、CSV 格式的病历元数据文件解析
"""

from __future__ import annotations

import csv
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from models import (
    EmrChapter,
    EmrTimestampRecord,
)


class ParserError(Exception):
    """解析器异常基类"""
    pass


class XmlParseError(ParserError):
    """XML 解析错误"""
    pass


class JsonParseError(ParserError):
    """JSON 解析错误"""
    pass


class CsvParseError(ParserError):
    """CSV 解析错误"""
    pass


def normalize_timestamp(value: Any) -> Optional[datetime]:
    """
    统一时间格式解析

    支持格式：
    - %Y-%m-%d %H:%M:%S
    - %Y-%m-%dT%H:%M:%S (ISO8601)
    - %Y-%m-%dT%H:%M:%S.%f
    - Unix timestamp (整数或字符串)

    Args:
        value: 时间值（字符串、整数或 datetime）

    Returns:
        datetime 对象，解析失败返回 None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, (int, float)):
        # Unix timestamp (秒)
        if value > 1e12:
            # 毫秒级时间戳
            value = value / 1000
        try:
            return datetime.fromtimestamp(value)
        except (ValueError, OSError):
            return None

    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        # 尝试多种时间格式
        formats = [
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        # 尝试作为 Unix 时间戳字符串
        try:
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000
            return datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            pass

    return None


class BaseParser(ABC):
    """解析器基类"""

    @abstractmethod
    def parse(self, content: str | Path) -> list[EmrTimestampRecord]:
        """解析内容并返回病历记录列表"""
        pass

    def _safe_get(self, data: dict, key: str, default: Any = None) -> Any:
        """安全获取字典值（支持点号路径如 'a.b.c'）"""
        if "." not in key:
            return data.get(key, default)

        parts = key.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return default
            if current is None:
                return default
        return current


class XmlParser(BaseParser):
    """XML 格式解析器"""

    def __init__(self):
        self._chapters_data: list[dict] = []

    def parse(self, content: str | Path) -> list[EmrTimestampRecord]:
        """解析 XML 文件"""
        try:
            import xml.etree.ElementTree as ET
        except ImportError:
            raise XmlParseError("需要 xml.etree.ElementTree 模块")

        if isinstance(content, Path):
            content = Path(content)
            if not content.exists():
                raise XmlParseError(f"文件不存在: {content}")
            try:
                tree = ET.parse(content)
                root = tree.getroot()
            except ET.ParseError as e:
                raise XmlParseError(f"XML 解析错误: {e}")
        else:
            try:
                root = ET.fromstring(content)
            except ET.ParseError as e:
                raise XmlParseError(f"XML 解析错误: {e}")

        records: list[EmrTimestampRecord] = []

        # 尝试多种可能的根元素和记录元素名称
        record_elements = self._find_all_records(root)

        for record_elem in record_elements:
            try:
                record = self._parse_record(record_elem)
                if record:
                    records.append(record)
            except Exception as e:
                # 跳过无效记录，记录解析错误
                continue

        return records

    def _find_all_records(self, root) -> list:
        """查找所有病历记录元素"""
        # 常见标签名
        record_tags = ["record", "emr_record", "emr", "patient_record",
                       "medical_record", "record_entry"]

        for tag in record_tags:
            found = root.findall(f".//{tag}")
            if found:
                return found

        # 如果没有找到，尝试将 root 作为单个记录
        if root.tag in record_tags:
            return [root]

        # 尝试直接子元素
        return list(root)

    def _parse_record(self, elem) -> Optional[EmrTimestampRecord]:
        """解析单个病历记录"""
        def get_text(subelem, tag, default=""):
            found = subelem.find(tag)
            return found.text.strip() if found is not None and found.text else default

        def get_attr(subelem, tag, attr, default=""):
            found = subelem.find(tag)
            if found is not None:
                val = found.get(attr, default)
                return val if val else default
            return default

        patient_id = get_text(elem, "patient_id") or get_attr(elem, "patient", "id")
        visit_id = get_text(elem, "visit_id") or get_attr(elem, "visit", "id")
        record_id = get_text(elem, "record_id") or elem.get("id", "")
        record_type = get_text(elem, "record_type") or get_text(elem, "type", "未知类型")

        if not patient_id:
            return None

        # 解析业务时间
        business_time_str = get_text(elem, "business_time")
        business_time = normalize_timestamp(business_time_str)

        # 解析章节
        chapters: list[EmrChapter] = []
        chapter_elements = elem.findall(".//chapter") + elem.findall(".//section")

        for idx, chap_elem in enumerate(chapter_elements):
            chapter_id = get_text(chap_elem, "chapter_id") or chap_elem.get("id", f"ch_{idx}")
            chapter_name = get_text(chap_elem, "chapter_name") or get_text(chap_elem, "name", f"章节{idx+1}")
            author_id = get_text(chap_elem, "author_id") or get_attr(chap_elem, "author", "id", "未知")

            created_str = get_text(chap_elem, "created_time") or get_text(chap_elem, "create_time")
            modified_str = get_text(chap_elem, "modified_time") or get_text(chap_elem, "modify_time")

            created_time = normalize_timestamp(created_str)
            modified_time = normalize_timestamp(modified_str) or created_time

            if created_time is None:
                created_time = datetime.now()
                modified_time = created_time

            try:
                chapter = EmrChapter(
                    chapter_id=chapter_id,
                    chapter_name=chapter_name,
                    chapter_order=idx,
                    created_time=created_time,
                    modified_time=modified_time,
                    author_id=author_id,
                )
                chapters.append(chapter)
            except ValueError:
                continue

        # 按 chapter_order 排序
        chapters.sort(key=lambda c: c.chapter_order)

        if not chapters:
            # 创建默认章节
            created_time = business_time or datetime.now()
            chapters.append(EmrChapter(
                chapter_id="default",
                chapter_name="默认章节",
                chapter_order=0,
                created_time=created_time,
                modified_time=created_time,
                author_id="未知",
            ))

        try:
            record = EmrTimestampRecord(
                patient_id=patient_id,
                visit_id=visit_id or "unknown",
                record_id=record_id or f"rec_{patient_id}_{visit_id}",
                record_type=record_type,
                chapters=chapters,
                business_time=business_time,
            )
            return record
        except ValueError:
            return None

    def _parse_chapters(self, elem) -> list[EmrChapter]:
        """从 XML 元素解析章节列表（兼容性别名）"""
        chapters: list[EmrChapter] = []
        chapter_elements = elem.findall(".//chapter")

        for idx, chap_elem in enumerate(chapter_elements):
            chapter_id = chap_elem.get("id", f"ch_{idx}")
            chapter_name = chap_elem.findtext("name", f"章节{idx+1}")

            created_str = chap_elem.findtext("created_time")
            modified_str = chap_elem.findtext("modified_time")

            created_time = normalize_timestamp(created_str)
            modified_time = normalize_timestamp(modified_str) or created_time

            author_id = chap_elem.findtext("author_id", "未知")

            if created_time:
                try:
                    chapter = EmrChapter(
                        chapter_id=chapter_id,
                        chapter_name=chapter_name,
                        chapter_order=idx,
                        created_time=created_time,
                        modified_time=modified_time or created_time,
                        author_id=author_id,
                    )
                    chapters.append(chapter)
                except ValueError:
                    continue

        return chapters


class JsonParser(BaseParser):
    """JSON 格式解析器"""

    def parse(self, content: str | Path) -> list[EmrTimestampRecord]:
        """解析 JSON 文件"""
        if isinstance(content, Path):
            if not content.exists():
                raise JsonParseError(f"文件不存在: {content}")
            try:
                with open(content, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                raise JsonParseError(f"JSON 解析错误: {e}")
            except IOError as e:
                raise JsonParseError(f"文件读取错误: {e}")
        else:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise JsonParseError(f"JSON 解析错误: {e}")

        # 支持多种 JSON 结构
        if isinstance(data, list):
            records_data = data
        elif isinstance(data, dict):
            # 尝试找到记录数组
            for key in ["records", "emr_records", "data", "items", "entries"]:
                if key in data and isinstance(data[key], list):
                    records_data = data[key]
                    break
            else:
                # 单个记录
                records_data = [data]
        else:
            raise JsonParseError("JSON 数据格式无效")

        records: list[EmrTimestampRecord] = []
        for idx, record_data in enumerate(records_data):
            try:
                record = self._parse_record(record_data)
                if record:
                    records.append(record)
            except Exception:
                continue

        return records

    def _parse_record(self, data: dict) -> Optional[EmrTimestampRecord]:
        """解析单个病历记录"""
        if not isinstance(data, dict):
            return None

        # 提取字段（支持多种可能的字段名）
        patient_id = (
            data.get("patient_id")
            or data.get("patientId")
            or data.get("patient")
        )
        visit_id = (
            data.get("visit_id")
            or data.get("visitId")
            or data.get("visit")
        )
        record_id = (
            data.get("record_id")
            or data.get("recordId")
            or data.get("id")
        )
        record_type = (
            data.get("record_type")
            or data.get("recordType")
            or data.get("type")
            or data.get("recordTypeName")
            or "未知类型"
        )

        if not patient_id:
            return None

        # 解析业务时间
        business_time_str = (
            data.get("business_time")
            or data.get("businessTime")
            or data.get("businessTimeValue")
        )
        business_time = normalize_timestamp(business_time_str)

        # 解析章节
        chapters: list[EmrChapter] = []
        chapters_data = (
            data.get("chapters")
            or data.get("sections")
            or data.get("chapterList")
            or []
        )

        for idx, chap_data in enumerate(chapters_data):
            if not isinstance(chap_data, dict):
                continue

            chapter_id = (
                chap_data.get("chapter_id")
                or chap_data.get("chapterId")
                or chap_data.get("id")
                or f"ch_{idx}"
            )
            chapter_name = (
                chap_data.get("chapter_name")
                or chap_data.get("chapterName")
                or chap_data.get("name")
                or f"章节{idx+1}"
            )
            author_id = (
                chap_data.get("author_id")
                or chap_data.get("authorId")
                or chap_data.get("author")
                or "未知"
            )

            created_str = (
                chap_data.get("created_time")
                or chap_data.get("createdTime")
                or chap_data.get("create_time")
            )
            modified_str = (
                chap_data.get("modified_time")
                or chap_data.get("modifiedTime")
                or chap_data.get("modify_time")
            )

            created_time = normalize_timestamp(created_str)
            modified_time = normalize_timestamp(modified_str) or created_time

            if created_time is None:
                created_time = datetime.now()
                modified_time = created_time

            try:
                chapter = EmrChapter(
                    chapter_id=str(chapter_id),
                    chapter_name=str(chapter_name),
                    chapter_order=idx,
                    created_time=created_time,
                    modified_time=modified_time,
                    author_id=str(author_id),
                )
                chapters.append(chapter)
            except ValueError:
                continue

        # 按 chapter_order 排序
        chapters.sort(key=lambda c: c.chapter_order)

        if not chapters:
            created_time = business_time or datetime.now()
            chapters.append(EmrChapter(
                chapter_id="default",
                chapter_name="默认章节",
                chapter_order=0,
                created_time=created_time,
                modified_time=created_time,
                author_id="未知",
            ))

        try:
            return EmrTimestampRecord(
                patient_id=str(patient_id),
                visit_id=str(visit_id or "unknown"),
                record_id=str(record_id or f"rec_{patient_id}_{visit_id}"),
                record_type=str(record_type),
                chapters=chapters,
                business_time=business_time,
            )
        except ValueError:
            return None

    def _parse_chapters(self, data: dict) -> list[EmrChapter]:
        """从 JSON 数据解析章节列表（兼容性别名）"""
        chapters: list[EmrChapter] = []
        chapters_data = data.get("chapters") or data.get("sections") or []

        for idx, chap_data in enumerate(chapters_data):
            if not isinstance(chap_data, dict):
                continue

            created_str = chap_data.get("created_time")
            modified_str = chap_data.get("modified_time")

            created_time = normalize_timestamp(created_str)
            modified_time = normalize_timestamp(modified_str) or created_time

            if created_time:
                try:
                    chapter = EmrChapter(
                        chapter_id=str(chap_data.get("id", f"ch_{idx}")),
                        chapter_name=str(chap_data.get("name", f"章节{idx+1}")),
                        chapter_order=idx,
                        created_time=created_time,
                        modified_time=modified_time or created_time,
                        author_id=str(chap_data.get("author", "未知")),
                    )
                    chapters.append(chapter)
                except ValueError:
                    continue

        return chapters


class CsvParser(BaseParser):
    """CSV 格式解析器"""

    def parse(self, content: str | Path) -> list[EmrTimestampRecord]:
        """解析 CSV 文件"""
        if isinstance(content, Path):
            if not content.exists():
                raise CsvParseError(f"文件不存在: {content}")

        # 确定文件路径
        file_path = content if isinstance(content, Path) else None

        try:
            if file_path:
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
            else:
                import io
                reader = csv.DictReader(io.StringIO(content))
                rows = list(reader)
        except csv.Error as e:
            raise CsvParseError(f"CSV 解析错误: {e}")
        except IOError as e:
            raise CsvParseError(f"文件读取错误: {e}")

        if not rows:
            raise CsvParseError("CSV 文件为空")

        records: list[EmrTimestampRecord] = []

        # 按 record_id 分组
        records_map: dict[str, list[dict]] = {}
        for row in rows:
            record_id = row.get("record_id") or row.get("recordId") or row.get("id", "")
            if record_id not in records_map:
                records_map[record_id] = []
            records_map[record_id].append(row)

        for record_id, record_rows in records_map.items():
            try:
                record = self._parse_record_rows(record_id, record_rows, rows[0].keys())
                if record:
                    records.append(record)
            except Exception:
                continue

        return records

    def _parse_record_rows(
        self, record_id: str, rows: list[dict], fieldnames
    ) -> Optional[EmrTimestampRecord]:
        """解析属于同一病历记录的多行 CSV 数据"""
        if not rows:
            return None

        first_row = rows[0]

        # 提取主记录字段
        patient_id = (
            first_row.get("patient_id")
            or first_row.get("patientId")
            or first_row.get("patient")
            or ""
        )
        visit_id = (
            first_row.get("visit_id")
            or first_row.get("visitId")
            or first_row.get("visit")
            or "unknown"
        )
        record_type = (
            first_row.get("record_type")
            or first_row.get("recordType")
            or first_row.get("type")
            or "未知类型"
        )

        business_time_str = (
            first_row.get("business_time")
            or first_row.get("businessTime")
        )
        business_time = normalize_timestamp(business_time_str)

        # 解析章节
        chapters: list[EmrChapter] = []
        for idx, row in enumerate(rows):
            chapter_id = row.get("chapter_id") or row.get("chapterId") or f"ch_{idx}"
            chapter_name = (
                row.get("chapter_name")
                or row.get("chapterName")
                or row.get("chapter")
                or row.get("name")
                or f"章节{idx+1}"
            )
            author_id = (
                row.get("author_id")
                or row.get("authorId")
                or row.get("author")
                or "未知"
            )

            created_str = (
                row.get("created_time")
                or row.get("createdTime")
                or row.get("create_time")
            )
            modified_str = (
                row.get("modified_time")
                or row.get("modifiedTime")
                or row.get("modify_time")
            )

            created_time = normalize_timestamp(created_str)
            modified_time = normalize_timestamp(modified_str) or created_time

            if created_time is None:
                created_time = datetime.now()
                modified_time = created_time

            try:
                chapter = EmrChapter(
                    chapter_id=str(chapter_id),
                    chapter_name=str(chapter_name),
                    chapter_order=idx,
                    created_time=created_time,
                    modified_time=modified_time,
                    author_id=str(author_id),
                )
                chapters.append(chapter)
            except ValueError:
                continue

        # 按 chapter_order 排序
        chapters.sort(key=lambda c: c.chapter_order)

        if not chapters:
            return None

        try:
            return EmrTimestampRecord(
                patient_id=str(patient_id),
                visit_id=str(visit_id),
                record_id=str(record_id),
                record_type=str(record_type),
                chapters=chapters,
                business_time=business_time,
            )
        except ValueError:
            return None

    def _parse_records(self, content: str | Path) -> list[EmrTimestampRecord]:
        """从 CSV 批量解析病历时间戳记录（兼容性别名）"""
        return self.parse(content)


class ParserFactory:
    """解析器工厂"""

    _parsers = {
        ".xml": XmlParser,
        ".json": JsonParser,
        ".csv": CsvParser,
    }

    @classmethod
    def get_parser(cls, file_path: str | Path) -> BaseParser:
        """
        根据文件扩展名返回对应解析器实例

        Args:
            file_path: 文件路径

        Returns:
            对应的解析器实例

        Raises:
            ValueError: 不支持的文件格式
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        parser_class = cls._parsers.get(ext)
        if parser_class is None:
            supported = ", ".join(cls._parsers.keys())
            raise ValueError(f"不支持的文件格式: {ext}，支持的格式: {supported}")

        return parser_class()


def parse_file(file_path: str | Path) -> list[EmrTimestampRecord]:
    """
    解析病历元数据文件

    Args:
        file_path: 文件路径（支持 XML、JSON、CSV）

    Returns:
        病历时间戳记录列表

    Raises:
        ParserError: 解析错误
    """
    path = Path(file_path)
    if not path.exists():
        raise ParserError(f"文件不存在: {path}")

    parser = ParserFactory.get_parser(path)
    return parser.parse(path)


def parse_directory(
    dir_path: str | Path,
    recursive: bool = False,
    extensions: Optional[list[str]] = None,
) -> list[EmrTimestampRecord]:
    """
    扫描目录下所有元数据文件，批量解析

    Args:
        dir_path: 目录路径
        recursive: 是否递归扫描子目录
        extensions: 只扫描指定扩展名（如 ['.xml', '.json']），None 表示全部

    Returns:
        所有解析出的病历时间戳记录列表
    """
    path = Path(dir_path)
    if not path.is_dir():
        raise ParserError(f"目录不存在或不是目录: {path}")

    if extensions is None:
        extensions = list(ParserFactory._parsers.keys())

    extensions = [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions]

    all_records: list[EmrTimestampRecord] = []

    pattern = "**/*" if recursive else "*"
    for ext in extensions:
        for file_path in path.glob(f"{pattern}{ext}"):
            if file_path.is_file():
                try:
                    records = parse_file(file_path)
                    all_records.extend(records)
                except ParserError:
                    # 跳过解析失败的文件
                    continue

    return all_records