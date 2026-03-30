/**
 * EMR Timestamp Archaeologist - report 命令
 * 生成 HTML 可视化报告
 */

import { Command } from 'commander';
import chalk from 'chalk';
import path from 'path';
import fs from 'fs';
import {
  spawnPythonProcess,
  ensureOutputDir,
  getPythonModulePath,
} from '../utils.js';

/**
 * 注册 report 子命令
 */
export function reportCommand(program: Command): void {
  program
    .command('report')
    .description('生成 HTML 可视化报告')
    .argument('<input>', '分析结果文件路径 (JSON 格式，由 analyze 命令生成)')
    .option('-o, --output <file>', '输出 HTML 报告路径', 'report.html')
    .option('-t, --template <file>', '自定义 HTML 模板路径', '')
    .option('--no-llm', '禁用 LLM 叙述')
    .option('-v, --verbose', '显示详细输出', false)
    .action(async (input: string, options: any) => {
      const verbose = options.verbose || process.env.VERBOSE === '1';

      console.log(chalk.cyan('\n📄 开始生成 HTML 报告...\n'));

      // 验证输入文件
      if (!fs.existsSync(input)) {
        console.error(chalk.red(`文件不存在: ${input}`));
        process.exit(1);
      }

      const inputPath = path.resolve(input);
      const outputPath = path.resolve(options.output);

      // 确保输出目录存在
      ensureOutputDir(path.dirname(outputPath));

      // 获取 Python 模块路径
      const pyModulePath = getPythonModulePath();
      const cliPyPath = path.join(pyModulePath, 'cli.py');

      // 构建参数
      const args: string[] = ['report', inputPath, '--output', outputPath];

      if (options.template) {
        args.push('--template', path.resolve(options.template));
      }

      if (options.noLlm) {
        args.push('--no-llm');
      }

      // 调用 Python CLI
      try {
        const result = await spawnPythonProcess(cliPyPath, args, { verbose });

        if (result.exitCode !== 0) {
          console.error(chalk.red('\n❌ 报告生成失败'));
          if (result.stderr) {
            console.error(chalk.yellow('错误信息:'), result.stderr);
          }
          process.exit(1);
        }

        // 检查输出文件
        if (fs.existsSync(outputPath)) {
          const stats = fs.statSync(outputPath);
          console.log(chalk.green(`\n✅ HTML 报告已生成:`));
          console.log(chalk.cyan(`   文件: ${outputPath}`));
          console.log(chalk.cyan(`   大小: ${(stats.size / 1024).toFixed(1)} KB`));
          console.log(chalk.gray(`\n   使用 ${chalk.bold('emr-archaeologist serve')} 命令预览报告\n`));
        } else {
          console.error(chalk.red('\n❌ 报告文件未生成'));
          process.exit(1);
        }
      } catch (error: any) {
        console.error(chalk.red('\n❌ 执行失败:'), error.message);
        if (verbose) {
          console.error(error.stack);
        }
        process.exit(1);
      }
    });
}
