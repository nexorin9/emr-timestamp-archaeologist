"""
单元测试：EMR 时间戳考古器 - Python CLI 入口脚本
测试命令行接口功能
"""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from io import StringIO

import pytest

# 添加 src/py 到路径以便导入
sys.path.insert(0, str(Path(__file__).parent.parent))

# 导入 CLI 模块
from cli import (
    setup_logging,
    validate_input_file,
    output_json,
    create_parser,
)


class TestSetupLogging:
    """测试 setup_logging 函数"""

    def test_setup_logging_basic(self) -> None:
        """测试基本日志配置"""
        logger = setup_logging(level="INFO")
        assert logger is not None
        assert logger.level == 20  # INFO = 20

    def test_setup_logging_verbose(self) -> None:
        """测试 verbose 模式"""
        logger = setup_logging(verbose=True)
        assert logger is not None
        assert logger.level == 10  # DEBUG = 10


class TestValidateInputFile:
    """测试 validate_input_file 函数"""

    def test_validate_nonexistent_file(self) -> None:
        """测试不存在的文件"""
        with pytest.raises(FileNotFoundError):
            validate_input_file("nonexistent_file.xml")

    def test_validate_invalid_extension(self) -> None:
        """测试不支持的文件扩展名"""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            temp_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                validate_input_file(temp_path)
            assert "不支持的文件格式" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_validate_valid_xml(self) -> None:
        """测试有效的 XML 文件"""
        with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as f:
            f.write(b"<test></test>")
            temp_path = f.name

        try:
            result = validate_input_file(temp_path)
            assert result.suffix.lower() == ".xml"
        finally:
            Path(temp_path).unlink()

    def test_validate_valid_json(self) -> None:
        """测试有效的 JSON 文件"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{"test": true}')
            temp_path = f.name

        try:
            result = validate_input_file(temp_path)
            assert result.suffix.lower() == ".json"
        finally:
            Path(temp_path).unlink()

    def test_validate_valid_csv(self) -> None:
        """测试有效的 CSV 文件"""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(b"col1,col2\n1,2")
            temp_path = f.name

        try:
            result = validate_input_file(temp_path)
            assert result.suffix.lower() == ".csv"
        finally:
            Path(temp_path).unlink()


class TestOutputJson:
    """测试 output_json 函数"""

    def test_output_json_pretty(self) -> None:
        """测试格式化 JSON 输出"""
        data = {"key": "value", "number": 42}
        result = output_json(data, pretty=True)
        parsed = json.loads(result)
        assert parsed == data
        assert "\n" in result  # 格式化后包含换行

    def test_output_json_compact(self) -> None:
        """测试紧凑 JSON 输出"""
        data = {"key": "value", "number": 42}
        result = output_json(data, pretty=False)
        parsed = json.loads(result)
        assert parsed == data
        assert "\n" not in result  # 紧凑格式不包含换行

    def test_output_json_to_file(self) -> None:
        """测试输出到文件"""
        data = {"test": "data", "timestamp": datetime.now().isoformat()}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = f.name

        try:
            result = output_json(data, output_path=temp_path, pretty=True)
            with open(temp_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            Path(temp_path).unlink()


class TestCreateParser:
    """测试命令行参数解析器"""

    def test_parser_with_no_args(self) -> None:
        """测试无参数时返回默认参数（无command）"""
        parser = create_parser()
        args = parser.parse_args([])
        # 当没有子命令时，args.command 为 None
        assert args.command is None

    def test_parser_analyze_command(self) -> None:
        """测试 analyze 子命令解析"""
        parser = create_parser()
        args = parser.parse_args(["analyze", "test.xml"])
        assert args.command == "analyze"
        assert args.input == "test.xml"

    def test_parser_report_command(self) -> None:
        """测试 report 子命令解析"""
        parser = create_parser()
        args = parser.parse_args(["report", "result.json", "-o", "report.html"])
        assert args.command == "report"
        assert args.input == "result.json"
        assert args.output == "report.html"

    def test_parser_analyze_with_output(self) -> None:
        """测试 analyze 子命令带输出参数"""
        parser = create_parser()
        args = parser.parse_args(["analyze", "data.xml", "-o", "output.json"])
        assert args.command == "analyze"
        assert args.input == "data.xml"
        assert args.output == "output.json"

    def test_parser_analyze_no_llm(self) -> None:
        """测试禁用 LLM 选项"""
        parser = create_parser()
        args = parser.parse_args(["analyze", "data.xml", "--no-llm"])
        assert args.command == "analyze"
        assert args.no_llm is True

    def test_parser_verbose_flag(self) -> None:
        """测试 verbose 标志"""
        parser = create_parser()
        args = parser.parse_args(["--verbose", "analyze", "data.xml"])
        assert args.verbose is True
        assert args.command == "analyze"

    def test_parser_log_level(self) -> None:
        """测试日志级别选项"""
        parser = create_parser()
        args = parser.parse_args(["--log-level", "DEBUG", "analyze", "data.xml"])
        assert args.log_level == "DEBUG"
        assert args.command == "analyze"

    def test_parser_quiet_mode(self) -> None:
        """测试安静模式选项"""
        parser = create_parser()
        args = parser.parse_args(["analyze", "data.xml", "--quiet"])
        assert args.quiet is True
