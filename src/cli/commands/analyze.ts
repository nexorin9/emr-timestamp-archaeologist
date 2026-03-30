/**
 * EMR Timestamp Archaeologist - analyze 命令
 * 分析病历数据，检测时间戳异常
 */

import { Command } from 'commander';
import chalk from 'chalk';
import path from 'path';
import fs from 'fs';
import {
  spawnPythonProcess,
  printResult,
  validateInputFile,
  ensureOutputDir,
  getPythonModulePath,
} from '../utils.js';

/**
 * 注册 analyze 子命令
 */
export function analyzeCommand(program: Command): void {
  program
    .command('analyze')
    .description('分析病历时间戳数据，检测异常模式')
    .argument('<input>', '输入文件路径 (XML/JSON/CSV 格式)')
    .option('-o, --output <file>', '输出结果文件路径 (JSON 格式)')
    .option('-f, --format <type>', '输出格式: json, table, simple', 'table')
    .option('--no-llm', '禁用 LLM 分析')
    .option('--detectors <list>', '启用的检测器列表 (逗号分隔)', '')
    .option('-v, --verbose', '显示详细输出', false)
    .action(async (input: string, options: any) => {
      const verbose = options.verbose || process.env.VERBOSE === '1';

      console.log(chalk.cyan('\n🔍 开始分析病历数据...\n'));

      // 验证输入文件
      if (!validateInputFile(input)) {
        process.exit(1);
      }

      const inputPath = path.resolve(input);

      // 获取 Python 模块路径
      const pyModulePath = getPythonModulePath();
      const cliPyPath = path.join(pyModulePath, 'cli.py');

      // 构建参数
      const args: string[] = ['analyze', inputPath];

      if (options.output) {
        const outputPath = path.resolve(options.output);
        ensureOutputDir(path.dirname(outputPath));
        args.push('--output', outputPath);
      }

      // Python CLI always outputs JSON, so we don't pass --format

      if (options.noLlm) {
        args.push('--no-llm');
      }

      if (options.detectors) {
        args.push('--detectors', options.detectors);
      }

      // 调用 Python CLI
      try {
        const result = await spawnPythonProcess(cliPyPath, args, { verbose });

        if (result.exitCode !== 0) {
          console.error(chalk.red('\n❌ 分析失败'));
          if (result.stderr) {
            console.error(chalk.yellow('错误信息:'), result.stderr);
          }
          process.exit(1);
        }

        // 解析并输出结果
        if (result.stdout) {
          try {
            const analysisResult = JSON.parse(result.stdout);

            // 如果指定了输出文件但不是 json 格式，仍然打印结果
            if (options.format !== 'json' || !options.output) {
              printResult(analysisResult, options.format || 'table');
            }

            // 保存到文件
            if (options.output && options.format === 'json') {
              fs.writeFileSync(options.output, result.stdout, 'utf-8');
              console.log(chalk.green(`\n✅ 结果已保存到: ${options.output}`));
            } else if (options.output) {
              // 将完整 JSON 结果保存
              fs.writeFileSync(options.output, JSON.stringify(analysisResult, null, 2), 'utf-8');
              console.log(chalk.green(`\n✅ 结果已保存到: ${options.output}`));
            }
          } catch {
            // 输出不是 JSON，直接打印
            console.log(result.stdout);
          }
        }

        console.log(chalk.green('\n✅ 分析完成\n'));
      } catch (error: any) {
        console.error(chalk.red('\n❌ 执行失败:'), error.message);
        if (verbose) {
          console.error(error.stack);
        }
        process.exit(1);
      }
    });
}
