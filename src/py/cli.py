"""
EMR Timestamp Archaeologist - Python CLI 入口脚本
接收 Node.js 传来的命令并执行分析
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加 src/py 目录到 Python 路径，以便导入模块（与测试文件相同的方式）
sys.path.insert(0, str(Path(__file__).parent))

# 导入项目模块
from parser import parse_file, parse_directory, ParserError
from detection_engine import create_detection_engine, run_detection, DetectionReport
from stratum_builder import build_stratum_map
from report_renderer import render_report
from debug_tools import (
    dump_stratum_map,
    visualize_timestamps,
    print_anomaly_details,
    debug_detector,
    export_detection_trace,
    benchmark_detectors,
    generate_detection_config,
    print_debug_banner,
)


# 全局日志记录器
logger: Optional[logging.Logger] = None


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    verbose: bool = False,
) -> logging.Logger:
    """
    配置日志

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 日志文件路径（可选）
        verbose: 是否为 verbose 模式

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    global logger

    # 确定日志级别
    if verbose:
        log_level = logging.DEBUG
    else:
        log_level = getattr(logging, level.upper(), logging.INFO)

    # 创建日志记录器
    logger = logging.getLogger("emr-archaeologist")
    logger.setLevel(log_level)

    # 清除已有的处理器
    logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def handle_interrupt(signum: int, frame) -> None:
    """
    优雅处理 KeyboardInterrupt

    Args:
        signum: 信号编号
        frame: 当前堆栈帧
    """
    if logger:
        logger.info("收到中断信号，正在优雅退出...")
    sys.exit(0)


def validate_input_file(file_path: str) -> Path:
    """
    验证输入文件是否存在且格式正确

    Args:
        file_path: 文件路径

    Returns:
        Path: 验证后的文件路径

    Raises:
        FileNotFoundError: 文件不存在
        ValueError: 文件格式不支持
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"输入文件不存在: {file_path}")

    if not path.is_file():
        raise ValueError(f"输入路径不是文件: {file_path}")

    # 检查文件扩展名
    supported_extensions = {".xml", ".json", ".csv"}
    if path.suffix.lower() not in supported_extensions:
        raise ValueError(
            f"不支持的文件格式: {path.suffix}，支持的格式: {', '.join(supported_extensions)}"
        )

    return path


def output_json(data: dict, output_path: Optional[str] = None, pretty: bool = True) -> str:
    """
    将分析结果输出为 JSON

    Args:
        data: 要输出的数据字典
        output_path: 输出文件路径（可选）
        pretty: 是否格式化输出

    Returns:
        str: JSON 字符串
    """
    if pretty:
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
    else:
        json_str = json.dumps(data, ensure_ascii=False)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(json_str)
        if logger:
            logger.info(f"结果已保存到: {output_path}")

    return json_str


def cmd_analyze(args: argparse.Namespace) -> int:
    """
    分析子命令：加载数据，运行检测引擎，输出 JSON 结果

    Args:
        args: 命令行参数命名空间

    Returns:
        int: 退出码（0 表示成功）
    """
    try:
        # 验证输入文件
        input_path = validate_input_file(args.input)

        # 解析数据
        if logger:
            logger.info(f"正在解析文件: {input_path}")

        if input_path.is_dir():
            records = parse_directory(input_path)
        else:
            records = parse_file(input_path)

        if logger:
            logger.info(f"成功解析 {len(records)} 条病历记录")

        if not records:
            if logger:
                logger.warning("未解析到任何病历记录")
            output_data = {
                "success": True,
                "record_count": 0,
                "anomaly_count": 0,
                "risk_score": 0.0,
                "risk_level": "极低",
                "anomalies": [],
                "timestamp": datetime.now().isoformat(),
            }
            print(output_json(output_data, args.output))
            return 0

        # 调试模式：显示时间戳可视化
        if args.debug:
            print_debug_banner("数据解析结果")
            visualize_timestamps(records)

        # 构建地层图
        if logger:
            logger.info("正在构建时序地层图...")
        stratum_map = build_stratum_map(records)

        # 调试模式：导出地层图
        if args.debug and stratum_map:
            debug_output_dir = Path(args.output).parent if args.output else Path(".")
            debug_output_dir.mkdir(parents=True, exist_ok=True)
            stratum_debug_path = debug_output_dir / "debug_stratum_map.json"
            dump_stratum_map(stratum_map, str(stratum_debug_path))

        # 运行检测引擎
        if logger:
            logger.info("正在运行异常检测...")

        llm_enabled = not args.no_llm
        engine = create_detection_engine(llm_enabled=llm_enabled)

        # 调试模式：逐检测器运行并显示中间结果
        if args.debug:
            print_debug_banner("逐检测器调试")
            from detectors import (
                BatchDetector,
                NightActivityDetector,
                TimeContradictionDetector,
                SequenceDetector,
            )

            detectors_to_debug = [
                ("batch", BatchDetector()),
                ("night", NightActivityDetector()),
                ("contradiction", TimeContradictionDetector()),
                ("sequence", SequenceDetector()),
            ]

            all_results = []
            for name, detector in detectors_to_debug:
                result = debug_detector(name, detector, records)
                all_results.append(result)

            # 导出检测追踪日志
            debug_output_dir = Path(args.output).parent if args.output else Path(".")
            trace_path = debug_output_dir / "debug_detection_trace.json"
            export_detection_trace(all_results, records, str(trace_path))

            # 性能基准测试
            print_debug_banner("检测器性能基准")
            benchmark_detectors(detectors_to_debug, records, iterations=5)

            # 配置推荐
            print_debug_banner("配置推荐")
            generate_detection_config(records)

        # 运行完整检测引擎
        anomalies = engine.run_all_detectors(records)

        if logger:
            logger.info(f"检测完成，发现 {len(anomalies)} 个异常")

        # 生成报告
        report = engine.generate_report_data()

        # 调试模式：打印异常详情
        if args.debug:
            print_debug_banner("异常详情")
            print_anomaly_details(report.top_anomalies if hasattr(report, 'top_anomalies') else [], verbose=True)

        # 构建输出数据
        output_data = {
            "success": True,
            "record_count": len(records),
            "anomaly_count": len(anomalies),
            "risk_score": report.overall_risk_score,
            "risk_level": report.risk_level,
            "anomalies_by_type": report.anomalies_by_type,
            "anomalies_by_severity": report.anomalies_by_severity,
            "top_anomalies": report.top_anomalies,
            "summary_stats": report.summary_stats,
            "timestamp": datetime.now().isoformat(),
            "stratum_map": stratum_map.to_dict() if stratum_map else None,
        }

        # 输出结果
        json_output = output_json(output_data, args.output)

        # 如果没有指定输出文件，且不是安静模式，则打印到控制台
        if not args.output and not args.quiet:
            print(json_output)

        return 0

    except FileNotFoundError as e:
        if logger:
            logger.error(f"文件错误: {e}")
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1
    except ParserError as e:
        if logger:
            logger.error(f"解析错误: {e}")
        print(json.dumps({"success": False, "error": f"解析错误: {e}"}, ensure_ascii=False))
        return 1
    except Exception as e:
        if logger:
            logger.exception(f"分析过程出错: {e}")
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def cmd_report(args: argparse.Namespace) -> int:
    """
    报告子命令：加载分析结果，调用 HTML 渲染器

    Args:
        args: 命令行参数命名空间

    Returns:
        int: 退出码（0 表示成功）
    """
    try:
        # 验证输入文件
        input_path = Path(args.input)
        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {args.input}")

        # 加载分析结果
        if logger:
            logger.info(f"正在加载分析结果: {input_path}")

        with open(input_path, "r", encoding="utf-8") as f:
            analysis_data = json.load(f)

        if not analysis_data.get("success"):
            raise ValueError(f"分析结果文件无效: {analysis_data.get('error', '未知错误')}")

        # 构建 DetectionReport 对象
        report = DetectionReport(
            total_records=analysis_data.get("record_count", 0),
            total_anomalies=analysis_data.get("anomaly_count", 0),
            overall_risk_score=analysis_data.get("risk_score", 0.0),
            risk_level=analysis_data.get("risk_level", "极低"),
            anomalies_by_type=analysis_data.get("anomalies_by_type", {}),
            anomalies_by_severity=analysis_data.get("anomalies_by_severity", {}),
            top_anomalies=analysis_data.get("top_anomalies", []),
            summary_stats=analysis_data.get("summary_stats", {}),
        )

        # 构建地层图（如果有）
        stratum_map = None
        if "stratum_map" in analysis_data and analysis_data["stratum_map"]:
            from stratum_builder import build_stratum_map
            from parser import parse_file, parse_directory

            # 需要重新解析记录来构建地层图
            # 尝试从原始数据目录加载
            data_dir = input_path.parent
            if data_dir.name == "data":
                records = parse_directory(data_dir)
                if records:
                    stratum_map = build_stratum_map(records)

        # 生成 HTML 报告
        if logger:
            logger.info(f"正在生成 HTML 报告: {args.output}")

        render_report(report, args.output, stratum_map)

        if logger:
            logger.info(f"报告已生成: {args.output}")

        return 0

    except FileNotFoundError as e:
        if logger:
            logger.error(f"文件错误: {e}")
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1
    except json.JSONDecodeError as e:
        if logger:
            logger.error(f"JSON 解析错误: {e}")
        print(json.dumps({"success": False, "error": f"JSON 解析错误: {e}"}, ensure_ascii=False))
        return 1
    except Exception as e:
        if logger:
            logger.exception(f"报告生成出错: {e}")
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        return 1


def create_parser() -> argparse.ArgumentParser:
    """
    创建命令行参数解析器

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    parser = argparse.ArgumentParser(
        prog="emr-archaeologist",
        description="EMR Timestamp Archaeologist - 病历时间戳考古器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s analyze data/sample.xml
  %(prog)s analyze data/sample.xml -o result.json
  %(prog)s analyze data/ -o result.json --no-llm
  %(prog)s report result.json -o report.html
        """,
    )

    # 全局选项
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="启用详细输出",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式（显示中间结果和追踪信息）",
    )
    parser.add_argument(
        "--log",
        type=str,
        default=None,
        help="日志文件路径",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="日志级别",
    )

    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # analyze 子命令
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="分析病历文件或目录",
        description="解析病历文件，运行异常检测，输出分析结果",
    )
    analyze_parser.add_argument(
        "input",
        type=str,
        help="输入文件路径（XML/JSON/CSV）或目录路径",
    )
    analyze_parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="输出文件路径（JSON 格式）",
    )
    analyze_parser.add_argument(
        "--no-llm",
        action="store_true",
        help="禁用 LLM 分析",
    )
    analyze_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="安静模式，不输出到控制台",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # report 子命令
    report_parser = subparsers.add_parser(
        "report",
        help="生成 HTML 报告",
        description="加载分析结果，生成 HTML 可视化报告",
    )
    report_parser.add_argument(
        "input",
        type=str,
        help="分析结果 JSON 文件路径",
    )
    report_parser.add_argument(
        "-o", "--output",
        type=str,
        default="report.html",
        help="输出 HTML 文件路径",
    )
    report_parser.set_defaults(func=cmd_report)

    return parser


def main() -> int:
    """
    主入口函数

    Returns:
        int: 退出码
    """
    global logger

    # 解析命令行参数
    parser = create_parser()
    args = parser.parse_args()

    # 如果没有指定命令，显示帮助信息
    if not args.command:
        parser.print_help()
        return 0

    # 设置日志
    setup_logging(
        level=args.log_level,
        log_file=args.log,
        verbose=args.verbose or args.debug,
    )

    # 注册信号处理器
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)

    # 执行子命令
    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())