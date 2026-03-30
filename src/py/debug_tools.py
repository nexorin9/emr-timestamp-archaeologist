"""
EMR Timestamp Archaeologist - 异常检测调试工具
提供调试和分析中间结果的功能，帮助开发者和高级用户调试检测规则
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from models import (
    AnomalyType,
    EmrChapter,
    EmrTimestampRecord,
    TimestampAnomaly,
)
from stratum_builder import StratumMap
from detection_engine import DetectionEngine, DetectorResult


# ANSI color codes for terminal output
class Colors:
    """Terminal color codes"""
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"


@dataclass
class DetectionTrace:
    """
    检测追踪日志条目

    Attributes:
        timestamp: 追踪时间戳
        detector_name: 检测器名称
        input_record_count: 输入记录数
        output_anomaly_count: 输出异常数
        execution_time_ms: 执行时间
        error: 错误信息（如果有）
        intermediate_data: 中间数据（用于调试）
    """
    timestamp: datetime
    detector_name: str
    input_record_count: int
    output_anomaly_count: int
    execution_time_ms: float
    error: Optional[str] = None
    intermediate_data: Optional[dict] = None


def dump_stratum_map(stratum_map: StratumMap, output_path: str) -> None:
    """
    将地层图导出为调试用的 JSON 文件

    Args:
        stratum_map: 地层图对象
        output_path: 输出文件路径
    """
    data = stratum_map.to_dict()

    # 添加额外的调试信息
    debug_info = {
        "exported_at": datetime.now().isoformat(),
        "record_count": len(stratum_map.records),
        "chapter_count": sum(len(r.chapters) for r in stratum_map.records.values()),
        "layer_count": len(stratum_map.layers),
        "timestamp_count": len(stratum_map.all_timestamps),
        "anchor_count": len(stratum_map.anchor_lines),
    }
    data["debug_info"] = debug_info

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    print(f"{Colors.GREEN}✓{Colors.RESET} 地层图已导出到: {output_path}")
    print(f"  - 记录数: {debug_info['record_count']}")
    print(f"  - 章节数: {debug_info['chapter_count']}")
    print(f"  - 地层数: {debug_info['layer_count']}")
    print(f"  - 时间戳数: {debug_info['timestamp_count']}")
    print(f"  - 锚点数: {debug_info['anchor_count']}")


def visualize_timestamps(records: list[EmrTimestampRecord], output: Optional[object] = None) -> None:
    """
    在终端打印 ASCII 时间线图

    Args:
        records: 病历时间戳记录列表
        output: 输出流（默认为 sys.stdout）
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    if not records:
        out(f"{Colors.YELLOW}警告: 没有记录可显示{Colors.RESET}\n")
        return

    # 收集所有时间戳并排序
    all_events: list[tuple[datetime, str, str, str]] = []  # (时间, 类型, record_id, 描述)

    for record in records:
        for chapter in record.chapters:
            event_type = "C" if chapter.created_time == chapter.modified_time else "M"
            all_events.append((
                chapter.created_time,
                event_type,
                record.record_id,
                f"{chapter.chapter_name}({chapter.chapter_id})"
            ))
            if chapter.created_time != chapter.modified_time:
                all_events.append((
                    chapter.modified_time,
                    "M",
                    record.record_id,
                    f"{chapter.chapter_name}(修改)"
                ))

        if record.business_time:
            all_events.append((
                record.business_time,
                "B",
                record.record_id,
                f"业务时间[{record.record_type}]"
            ))

    # 按时间排序
    all_events.sort(key=lambda x: x[0])

    if not all_events:
        out(f"{Colors.YELLOW}警告: 没有时间戳事件可显示{Colors.RESET}\n")
        return

    # 计算时间范围
    start_time = all_events[0][0]
    end_time = all_events[-1][0]
    time_range = (end_time - start_time).total_seconds()

    out(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    out(f"{Colors.CYAN}{Colors.BOLD}  病历时间戳考古时间线{Colors.RESET}\n")
    out(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n\n")

    # 图例
    out(f"{Colors.GRAY}图例:{Colors.RESET} ")
    out(f"{Colors.GREEN}C{Colors.RESET}=创建 ")
    out(f"{Colors.YELLOW}M{Colors.RESET}=修改 ")
    out(f"{Colors.MAGENTA}B{Colors.RESET}=业务时间\n\n")

    # 时间线头部
    out(f"{Colors.WHITE}{start_time.strftime('%Y-%m-%d %H:%M:%S'):<20}{Colors.RESET}")
    out(" " * 60)
    out(f"{Colors.WHITE}{end_time.strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}\n")
    out(f"{Colors.GRAY}{'-'*80}{Colors.RESET}\n")

    # 打印时间线事件（限制显示数量）
    max_events = 50
    displayed_events = all_events[:max_events]
    omitted = len(all_events) - max_events

    current_date = None
    for i, (dt, event_type, record_id, description) in enumerate(displayed_events):
        # 日期分隔线
        date_str = dt.strftime("%Y-%m-%d")
        if current_date != date_str:
            current_date = date_str
            out(f"\n{Colors.BLUE}{date_str}{Colors.RESET}\n")

        # 计算位置（简化显示）
        if time_range > 0:
            progress = (dt - start_time).total_seconds() / time_range
            pos = int(progress * 60)
            bar = " " * pos + "|"
        else:
            bar = "|"

        # 颜色和符号
        if event_type == "C":
            color = Colors.GREEN
            symbol = "+"
        elif event_type == "M":
            color = Colors.YELLOW
            symbol = "*"
        else:
            color = Colors.MAGENTA
            symbol = "●"

        # 时间部分
        time_str = dt.strftime("%H:%M:%S")
        out(f"{color}{time_str}{Colors.RESET} {bar} {color}{symbol}{Colors.RESET} ")
        out(f"{color}{description[:30]}{Colors.RESET}")
        out(f"{Colors.GRAY} [{record_id[:8]}]{Colors.RESET}\n")

    if omitted > 0:
        out(f"\n{Colors.YELLOW}... 还有 {omitted} 个事件未显示{Colors.RESET}\n")

    out(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    out(f"总计: {len(all_events)} 个时间事件, {len(records)} 条记录\n\n")


def print_anomaly_details(
    anomalies: list[TimestampAnomaly],
    output: Optional[object] = None,
    verbose: bool = False
) -> None:
    """
    格式化打印异常详情

    Args:
        anomalies: 异常列表
        output: 输出流（默认为 sys.stdout）
        verbose: 是否显示详细信息
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    if not anomalies:
        out(f"{Colors.GREEN}✓ 没有检测到异常{Colors.RESET}\n")
        return

    # 按类型分组
    by_type: dict[str, list[TimestampAnomaly]] = {}
    for anomaly in anomalies:
        type_name = anomaly.anomaly_type.value if isinstance(anomaly.anomaly_type, AnomalyType) else str(anomaly.anomaly_type)
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(anomaly)

    out(f"\n{Colors.RED}{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    out(f"{Colors.RED}{Colors.BOLD}  检测到 {len(anomalies)} 个异常{Colors.RESET}\n")
    out(f"{Colors.RED}{'='*80}{Colors.RESET}\n\n")

    # 异常类型统计
    out(f"{Colors.CYAN}异常类型分布:{Colors.RESET}\n")
    for type_name, type_anomalies in sorted(by_type.items(), key=lambda x: -len(x[1])):
        color = _get_severity_color(type_anomalies[0].severity)
        out(f"  {color}●{Colors.RESET} {type_name}: {len(type_anomalies)} 个\n")
    out("\n")

    # 详细列表
    for i, anomaly in enumerate(anomalies, 1):
        severity_color = _get_severity_color(anomaly.severity)

        out(f"{i}. {Colors.BOLD}{anomaly.anomaly_type.value if isinstance(anomaly.anomaly_type, AnomalyType) else anomaly.anomaly_type}{Colors.RESET}\n")
        out(f"   {Colors.GRAY}严重程度:{Colors.RESET} {severity_color}{anomaly.severity}{Colors.RESET}/100\n")
        out(f"   {Colors.GRAY}描述:{Colors.RESET} {anomaly.description}\n")

        if verbose:
            out(f"   {Colors.GRAY}受影响记录:{Colors.RESET}\n")
            for record_id in anomaly.affected_records[:10]:
                out(f"     - {record_id}\n")
            if len(anomaly.affected_records) > 10:
                out(f"     {Colors.YELLOW}... 还有 {len(anomaly.affected_records) - 10} 条{Colors.RESET}\n")

            if anomaly.evidence:
                out(f"   {Colors.GRAY}证据:{Colors.RESET}\n")
                for evidence in anomaly.evidence[:5]:
                    out(f"     • {evidence}\n")

        out("\n")


def _get_severity_color(severity: float) -> str:
    """根据严重程度返回颜色"""
    if severity >= 80:
        return Colors.RED
    elif severity >= 60:
        return Colors.YELLOW
    elif severity >= 40:
        return Colors.CYAN
    else:
        return Colors.GREEN


def debug_detector(
    detector_name: str,
    detector_func: object,
    records: list[EmrTimestampRecord],
    output: Optional[object] = None
) -> DetectorResult:
    """
    逐检测器运行并打印中间结果

    Args:
        detector_name: 检测器名称
        detector_func: 检测器函数或对象
        records: 病历记录列表
        output: 输出流

    Returns:
        DetectorResult: 检测结果
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    out(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.RESET}\n")
    out(f"{Colors.CYAN}调试检测器: {detector_name}{Colors.RESET}\n")
    out(f"{Colors.CYAN}{'='*60}{Colors.RESET}\n\n")

    out(f"{Colors.GRAY}输入记录数: {len(records)}{Colors.RESET}\n")
    if not records:
        out(f"{Colors.YELLOW}警告: 输入记录为空{Colors.RESET}\n")
        return DetectorResult(detector_name=detector_name, anomalies=[], execution_time_ms=0.0)

    # 准备检测函数
    if hasattr(detector_func, 'detect'):
        detect_fn = detector_func.detect
    else:
        detect_fn = detector_func

    # 执行检测
    start_time = time.perf_counter()
    try:
        anomalies = detect_fn(records)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        out(f"{Colors.GREEN}✓ 检测完成{Colors.RESET}\n")
        out(f"{Colors.GRAY}执行时间: {elapsed_ms:.2f} ms{Colors.RESET}\n")
        out(f"{Colors.GRAY}检测到异常: {len(anomalies)} 个{Colors.RESET}\n\n")

        # 打印异常摘要
        if anomalies:
            by_type: dict[str, int] = {}
            for a in anomalies:
                type_name = a.anomaly_type.value if isinstance(a.anomaly_type, AnomalyType) else str(a.anomaly_type)
                by_type[type_name] = by_type.get(type_name, 0) + 1

            out(f"{Colors.CYAN}异常类型分布:{Colors.RESET}\n")
            for type_name, count in sorted(by_type.items(), key=lambda x: -x[1]):
                out(f"  • {type_name}: {count}\n")
            out("\n")

        result = DetectorResult(
            detector_name=detector_name,
            anomalies=anomalies,
            execution_time_ms=elapsed_ms,
        )

    except Exception as e:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        out(f"{Colors.RED}✗ 检测出错{Colors.RESET}\n")
        out(f"{Colors.RED}错误: {str(e)}{Colors.RESET}\n")

        result = DetectorResult(
            detector_name=detector_name,
            anomalies=[],
            execution_time_ms=elapsed_ms,
            error=str(e),
        )

    return result


def export_detection_trace(
    detector_results: list[DetectorResult],
    records: list[EmrTimestampRecord],
    output_path: str
) -> None:
    """
    导出检测追踪日志（每个检测器的输入输出）

    Args:
        detector_results: 检测器结果列表
        records: 原始输入记录
        output_path: 输出文件路径
    """
    trace_entries: list[dict] = []

    for result in detector_results:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "detector_name": result.detector_name,
            "input_record_count": len(records),
            "output_anomaly_count": len(result.anomalies),
            "execution_time_ms": result.execution_time_ms,
            "error": result.error,
            "anomalies": [a.to_dict() for a in result.anomalies],
        }
        trace_entries.append(entry)

    trace_data = {
        "exported_at": datetime.now().isoformat(),
        "total_records": len(records),
        "total_detectors": len(detector_results),
        "total_anomalies": sum(len(r.anomalies) for r in detector_results),
        "total_execution_time_ms": sum(r.execution_time_ms for r in detector_results),
        "records_sample": [
            {
                "record_id": r.record_id,
                "patient_id": r.patient_id,
                "visit_id": r.visit_id,
                "chapter_count": len(r.chapters),
                "business_time": r.business_time.isoformat() if r.business_time else None,
            }
            for r in records[:10]  # 只保存前10条记录的摘要
        ],
        "trace_entries": trace_entries,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(trace_data, f, ensure_ascii=False, indent=2, default=str)

    print(f"{Colors.GREEN}✓{Colors.RESET} 检测追踪日志已导出到: {output_path}")
    print(f"  - 检测器数: {trace_data['total_detectors']}")
    print(f"  - 总异常数: {trace_data['total_anomalies']}")
    print(f"  - 总执行时间: {trace_data['total_execution_time_ms']:.2f} ms")


def benchmark_detectors(
    detectors: list[tuple[str, object]],
    records: list[EmrTimestampRecord],
    iterations: int = 10,
    output: Optional[object] = None
) -> dict[str, dict]:
    """
    性能基准测试（检测器运行时间统计）

    Args:
        detectors: 检测器列表 [(名称, 检测器对象)]
        records: 病历记录列表
        iterations: 迭代次数
        output: 输出流

    Returns:
        dict: 基准测试结果
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    results: dict[str, dict] = {}

    out(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")
    out(f"{Colors.CYAN}{Colors.BOLD}  检测器性能基准测试{Colors.RESET}\n")
    out(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")

    out(f"{Colors.GRAY}测试配置: {len(records)} 条记录 × {iterations} 次迭代{Colors.RESET}\n\n")

    # 表头
    out(f"{Colors.WHITE}{'检测器':<25} {'平均时间':<15} {'最小时间':<15} {'最大时间':<15}{Colors.RESET}\n")
    out(f"{Colors.GRAY}{'-'*70}{Colors.RESET}\n")

    for name, detector in detectors:
        times: list[float] = []

        # 准备检测函数
        if hasattr(detector, 'detect'):
            detect_fn = detector.detect
        else:
            detect_fn = detector

        # 预热
        try:
            detect_fn(records[:min(10, len(records))])
        except Exception:
            pass

        # 实际测试
        for i in range(iterations):
            start = time.perf_counter()
            try:
                detect_fn(records)
            except Exception:
                pass
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        if times:
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)

            results[name] = {
                "avg_ms": avg_time,
                "min_ms": min_time,
                "max_ms": max_time,
                "iterations": iterations,
            }

            out(f"{Colors.CYAN}{name:<25}{Colors.RESET} ")
            out(f"{Colors.GREEN}{avg_time:>10.2f} ms{Colors.RESET}   ")
            out(f"{min_time:>10.2f} ms   ")
            out(f"{max_time:>10.2f} ms\n")
        else:
            out(f"{Colors.RED}{name:<25} 测试失败{Colors.RESET}\n")
            results[name] = {"error": "Benchmark failed"}

    out(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")

    return results


def compare_records(
    record1: EmrTimestampRecord,
    record2: EmrTimestampRecord,
    output: Optional[object] = None
) -> None:
    """
    对比两份病历记录的时间戳差异

    Args:
        record1: 第一条病历记录
        record2: 第二条病历记录
        output: 输出流
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    out(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")
    out(f"{Colors.CYAN}{Colors.BOLD}  病历记录对比{Colors.RESET}\n")
    out(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")

    # 基本信息
    out(f"{Colors.WHITE}记录 1:{Colors.RESET} {record1.record_id}\n")
    out(f"  患者: {record1.patient_id}, 就诊: {record1.visit_id}\n")
    out(f"  类型: {record1.record_type}\n")
    out(f"  章节数: {len(record1.chapters)}\n")

    out(f"\n{Colors.WHITE}记录 2:{Colors.RESET} {record2.record_id}\n")
    out(f"  患者: {record2.patient_id}, 就诊: {record2.visit_id}\n")
    out(f"  类型: {record2.record_type}\n")
    out(f"  章节数: {len(record2.chapters)}\n")

    # 章节对比
    out(f"\n{Colors.YELLOW}{Colors.BOLD}章节对比:{Colors.RESET}\n")
    out(f"{Colors.GRAY}{'章节ID':<20} {'记录1时间':<22} {'记录2时间':<22} {'差异':<10}{Colors.RESET}\n")
    out(f"{Colors.GRAY}{'-'*74}{Colors.RESET}\n")

    chapters1 = {c.chapter_id: c for c in record1.chapters}
    chapters2 = {c.chapter_id: c for c in record2.chapters}

    all_ids = sorted(set(chapters1.keys()) | set(chapters2.keys()))

    for chapter_id in all_ids:
        c1 = chapters1.get(chapter_id)
        c2 = chapters2.get(chapter_id)

        if c1 and c2:
            time1 = c1.created_time.strftime("%Y-%m-%d %H:%M:%S")
            time2 = c2.created_time.strftime("%Y-%m-%d %H:%M:%S")
            diff_seconds = (c1.created_time - c2.created_time).total_seconds()

            if abs(diff_seconds) < 1:
                diff_str = f"{Colors.GREEN}相同{Colors.RESET}"
            else:
                diff_str = f"{Colors.YELLOW}{diff_seconds:+.0f}秒{Colors.RESET}"

            out(f"{chapter_id:<20} {time1:<22} {time2:<22} {diff_str}\n")
        elif c1:
            time1 = c1.created_time.strftime("%Y-%m-%d %H:%M:%S")
            out(f"{chapter_id:<20} {time1:<22} {Colors.RED}{(None):<22}{Colors.RESET} {Colors.RED}仅记录1{Colors.RESET}\n")
        else:
            time2 = c2.created_time.strftime("%Y-%m-%d %H:%M:%S")
            out(f"{chapter_id:<20} {Colors.RED}{(None):<22}{Colors.RESET} {time2:<22} {Colors.RED}仅记录2{Colors.RESET}\n")

    out(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")


def generate_detection_config(
    records: list[EmrTimestampRecord],
    output: Optional[object] = None
) -> dict:
    """
    根据数据特征推荐最优检测器配置

    Args:
        records: 病历记录列表
        output: 输出流

    Returns:
        dict: 推荐的检测器配置
    """
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    # 分析数据特征
    total_records = len(records)
    total_chapters = sum(len(r.chapters) for r in records)

    # 夜间活动分析
    night_count = 0
    for record in records:
        for chapter in record.chapters:
            hour = chapter.created_time.hour
            if hour >= 22 or hour < 5:
                night_count += 1

    night_ratio = night_count / total_chapters if total_chapters > 0 else 0

    # 业务时间覆盖
    records_with_business_time = sum(1 for r in records if r.business_time is not None)

    # 时间戳密度
    timestamps = []
    for record in records:
        for chapter in record.chapters:
            timestamps.append(chapter.created_time)
    timestamps.sort()

    if len(timestamps) > 1:
        time_diffs = [(timestamps[i+1] - timestamps[i]).total_seconds()
                      for i in range(len(timestamps)-1)]
        avg_time_diff = sum(time_diffs) / len(time_diffs) if time_diffs else 0
    else:
        avg_time_diff = 0

    out(f"\n{Colors.CYAN}{Colors.BOLD}{'='*70}{Colors.RESET}\n")
    out(f"{Colors.CYAN}{Colors.BOLD}  数据特征分析与配置推荐{Colors.RESET}\n")
    out(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")

    # 数据特征
    out(f"{Colors.YELLOW}数据特征:{Colors.RESET}\n")
    out(f"  • 总记录数: {total_records}\n")
    out(f"  • 总章节数: {total_chapters}\n")
    out(f"  • 夜间章节比例: {night_ratio:.1%}\n")
    out(f"  • 有业务时间的记录: {records_with_business_time}/{total_records}\n")
    out(f"  • 平均时间戳间隔: {avg_time_diff:.0f} 秒\n\n")

    # 推荐配置
    out(f"{Colors.YELLOW}推荐检测器配置:{Colors.RESET}\n")

    config: dict = {
        "enabled_detectors": [],
        "detector_settings": {},
    }

    # 批处理检测 - 数据量大时启用
    if total_records > 50:
        out(f"  {Colors.GREEN}✓{Colors.RESET} 批处理检测: {Colors.GREEN}启用{Colors.RESET} (记录数较多)\n")
        config["enabled_detectors"].append("batch")
        config["detector_settings"]["batch"] = {"threshold_seconds": 60}
    else:
        out(f"  {Colors.GRAY}○{Colors.RESET} 批处理检测: {Colors.GRAY}跳过{Colors.RESET} (记录数较少)\n")

    # 夜间检测 - 夜间比例高时启用
    if night_ratio > 0.1:
        out(f"  {Colors.GREEN}✓{Colors.RESET} 夜间检测: {Colors.GREEN}启用{Colors.RESET} (夜间活动较多)\n")
        config["enabled_detectors"].append("night")
        config["detector_settings"]["night"] = {"night_start": 22, "night_end": 5}
    elif night_ratio > 0.05:
        out(f"  {Colors.YELLOW}△{Colors.RESET} 夜间检测: {Colors.YELLOW}建议启用{Colors.RESET} (有少量夜间活动)\n")
        config["enabled_detectors"].append("night")
        config["detector_settings"]["night"] = {"night_start": 22, "night_end": 5}
    else:
        out(f"  {Colors.GRAY}○{Colors.RESET} 夜间检测: {Colors.GRAY}跳过{Colors.RESET} (夜间活动极少)\n")

    # 矛盾检测 - 有业务时间时启用
    if records_with_business_time > 0:
        out(f"  {Colors.GREEN}✓{Colors.RESET} 矛盾检测: {Colors.GREEN}启用{Colors.RESET} (有业务时间锚点)\n")
        config["enabled_detectors"].append("contradiction")
        config["detector_settings"]["contradiction"] = {"max_time_gap_minutes": 120}
    else:
        out(f"  {Colors.YELLOW}△{Colors.RESET} 矛盾检测: {Colors.YELLOW}建议配置业务时间{Colors.RESET}\n")
        config["enabled_detectors"].append("contradiction")

    # 序列检测 - 始终启用
    out(f"  {Colors.GREEN}✓{Colors.RESET} 序列检测: {Colors.GREEN}启用{Colors.RESET} (基础检测)\n")
    config["enabled_detectors"].append("sequence")
    config["detector_settings"]["sequence"] = {
        "rushed_threshold_minutes": 5,
        "periodic_confidence_threshold": 0.7
    }

    out(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}\n\n")

    return config


def print_debug_banner(title: str, output: Optional[object] = None) -> None:
    """打印调试工具横幅"""
    if output is None:
        output = sys.stdout

    out = output.write if hasattr(output, 'write') else print

    out(f"\n{Colors.MAGENTA}{Colors.BOLD}")
    out("╔" + "═" * 60 + "╗\n")
    out(f"║  EMR Timestamp Archaeologist - 调试工具              ║\n")
    out(f"║  {title:<50} ║\n")
    out("╚" + "═" * 60 + "╝")
    out(f"{Colors.RESET}\n")
