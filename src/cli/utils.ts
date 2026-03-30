/**
 * EMR Timestamp Archaeologist - CLI 共享工具函数
 */

import { spawn, SpawnOptions } from 'child_process';
import { fileURLToPath } from 'url';
import chalk from 'chalk';
import figlet from 'figlet';
import path from 'path';
import fs from 'fs';
import os from 'os';

// 配置目录
const CONFIG_DIR = path.join(os.homedir(), '.emr-archaeologist');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');

export interface CliConfig {
  apiKey?: string;
  apiProvider?: 'openai' | 'anthropic';
  model?: string;
  llmEnabled?: boolean;
  verbose?: boolean;
}

/**
 * 打印程序 banner
 */
export function printBanner(): void {
  console.log(
    chalk.cyan(
      figlet.textSync('EMR Archaeologist', {
        font: 'Standard',
        horizontalLayout: 'default',
        verticalLayout: 'default',
      })
    )
  );
  console.log(chalk.yellow('  病历时间戳考古器 - 用考古学方法分析电子病历'));
  console.log(chalk.gray('  检测倒填时间、突击补写、批处理造假等异常模式\n'));
}

/**
 * 加载配置文件
 */
export function loadConfig(): CliConfig {
  try {
    if (fs.existsSync(CONFIG_DIR) && fs.existsSync(CONFIG_FILE)) {
      const data = fs.readFileSync(CONFIG_FILE, 'utf-8');
      return JSON.parse(data);
    }
  } catch (error) {
    if (process.env.VERBOSE) {
      console.error(chalk.yellow('加载配置文件失败:'), error);
    }
  }
  return {};
}

/**
 * 保存配置文件
 */
export function saveConfig(config: CliConfig): void {
  try {
    if (!fs.existsSync(CONFIG_DIR)) {
      fs.mkdirSync(CONFIG_DIR, { recursive: true });
    }
    fs.writeFileSync(CONFIG_FILE, JSON.stringify(config, null, 2), 'utf-8');
  } catch (error) {
    throw new Error(`保存配置文件失败: ${error}`);
  }
}

/**
 * 从 Node.js 调用 Python 分析脚本
 */
export function spawnPythonProcess(
  scriptPath: string,
  args: string[],
  options: { verbose?: boolean; input?: string } = {}
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return new Promise((resolve, reject) => {
    const verbose = options.verbose || process.env.VERBOSE === '1';

    // 确定 Python 命令
    const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';

    const spawnOptions: SpawnOptions = {
      stdio: options.input ? ['pipe', 'pipe', 'pipe'] : ['ignore', 'pipe', 'pipe'],
    };

    const child = spawn(pythonCmd, [scriptPath, ...args], spawnOptions);

    let stdout = '';
    let stderr = '';

    if (options.input) {
      child.stdin?.write(options.input);
      child.stdin?.end();
    }

    child.stdout?.on('data', (data) => {
      stdout += data.toString();
      if (verbose) {
        process.stdout.write(data);
      }
    });

    child.stderr?.on('data', (data) => {
      stderr += data.toString();
      if (verbose) {
        process.stderr.write(chalk.yellow(data.toString()));
      }
    });

    child.on('error', (error) => {
      reject(new Error(`启动 Python 进程失败: ${error.message}`));
    });

    child.on('close', (code) => {
      resolve({
        stdout,
        stderr,
        exitCode: code ?? 0,
      });
    });
  });
}

/**
 * 格式化输出分析结果到终端
 */
export function printResult(result: any, format: 'json' | 'table' | 'simple' = 'table'): void {
  if (format === 'json') {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  if (format === 'simple') {
    console.log(chalk.bold('\n分析结果:'));
    console.log(chalk.gray('─'.repeat(50)));
    if (result.summary) {
      console.log(`总记录数: ${chalk.green(result.summary.total_records || 0)}`);
      console.log(`总异常数: ${chalk.red(result.summary.total_anomalies || 0)}`);
      console.log(`风险评分: ${getRiskColor(result.summary.risk_score || 0)}`);
      console.log(`风险等级: ${getRiskLabel(result.summary.risk_level || 'unknown')}`);
    }
    return;
  }

  // table 格式
  console.log(chalk.bold('\n分析结果:'));
  console.log(chalk.gray('─'.repeat(60)));

  if (result.summary) {
    const summary = result.summary;
    console.log(chalk.cyan('\n  📊 统计摘要'));
    console.log(`    总记录数     : ${chalk.green(summary.total_records || 0)}`);
    console.log(`    总异常数     : ${chalk.red(summary.total_anomalies || 0)}`);
    console.log(`    风险评分     : ${getRiskColor(summary.risk_score || 0)} (${summary.risk_score || 0}/100)`);
    console.log(`    风险等级     : ${getRiskLabel(summary.risk_level || 'unknown')}`);
  }

  if (result.anomaly_types) {
    console.log(chalk.cyan('\n  🔍 异常类型分布'));
    for (const [type, count] of Object.entries(result.anomaly_types as Record<string, number>)) {
      const typeName = getAnomalyTypeName(type);
      console.log(`    ${typeName} : ${chalk.yellow(count as unknown as string)}`);
    }
  }

  if (result.top_anomalies && result.top_anomalies.length > 0) {
    console.log(chalk.cyan('\n  ⚠️  高风险异常 (前5条)'));
    for (let i = 0; i < Math.min(5, result.top_anomalies.length); i++) {
      const anomaly = result.top_anomalies[i];
      const severity = anomaly.severity || 0;
      console.log(`    ${i + 1}. [${getAnomalyTypeName(anomaly.anomaly_type)}] ${chalk.red(anomaly.description || '')}`);
      console.log(`       严重程度: ${getRiskColor(severity)} | 影响记录: ${anomaly.affected_records?.length || 0}`);
    }
  }

  console.log(chalk.gray('─'.repeat(60)));
}

/**
 * 获取风险等级颜色
 */
export function getRiskColor(score: number): string {
  if (score >= 80) return chalk.red(`⚠️ ${score}`);
  if (score >= 60) return chalk.red(`${score}`);
  if (score >= 40) return chalk.yellow(`${score}`);
  if (score >= 20) return chalk.blue(`${score}`);
  return chalk.green(`${score}`);
}

/**
 * 获取风险等级标签
 */
export function getRiskLabel(level: string): string {
  const labels: Record<string, string> = {
    '极低': chalk.green('极低'),
    '低': chalk.green('低'),
    '中等': chalk.yellow('中等'),
    '高': chalk.red('高'),
    '很高': chalk.red('很高'),
    '极高': chalk.bgRed.white('极高'),
    'unknown': chalk.gray('未知'),
  };
  return labels[level] || level;
}

/**
 * 获取异常类型名称
 */
export function getAnomalyTypeName(type: string): string {
  const names: Record<string, string> = {
    'BATCH_PROCESSING': '批处理痕迹',
    'NIGHT_RUSH': '夜间突击补写',
    'TIME_CONTRADICTION': '时间线矛盾',
    'SUSPICIOUS_SEQUENCE': '异常序列模式',
    'ANCHOR_VIOLATION': '锚点违规',
  };
  return names[type] || type;
}

/**
 * 获取 Python 模块路径
 */
export function getPythonModulePath(): string {
  // 使用 fileURLToPath 正确处理跨平台 file:// URL
  const currentFile = fileURLToPath(import.meta.url);
  // 从 dist/cli/index.js 向上两级到项目根目录
  const projectRoot = path.resolve(currentFile, '..', '..', '..');
  return path.join(projectRoot, 'src', 'py');
}

/**
 * 验证输入文件
 */
export function validateInputFile(filePath: string): boolean {
  if (!fs.existsSync(filePath)) {
    console.error(chalk.red(`文件不存在: ${filePath}`));
    return false;
  }

  const ext = path.extname(filePath).toLowerCase();
  const validExtensions = ['.xml', '.json', '.csv'];

  if (!validExtensions.includes(ext)) {
    console.error(chalk.red(`不支持的文件格式: ${ext}`));
    console.log(chalk.yellow(`支持的格式: ${validExtensions.join(', ')}`));
    return false;
  }

  return true;
}

/**
 * 确保输出目录存在
 */
export function ensureOutputDir(dirPath: string): void {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}
