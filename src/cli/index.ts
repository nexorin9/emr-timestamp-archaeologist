#!/usr/bin/env node

/**
 * EMR Timestamp Archaeologist - CLI 主入口
 * 病历时间戳考古器命令行界面
 */

import { Command } from 'commander';
import chalk from 'chalk';

import { analyzeCommand } from './commands/analyze.js';
import { reportCommand } from './commands/report.js';
import { serveCommand } from './commands/serve.js';
import { configCommand } from './commands/config.js';
import { printBanner } from './utils.js';

// 获取版本号
const version = '1.0.0';

// 创建主程序
const program = new Command();

// 全局选项
program
  .name('emr-archaeologist')
  .description(chalk.cyan('病历时间戳考古器 - 用考古学方法分析电子病历时间戳'))
  .version(version)
  .option('-v, --verbose', '输出详细调试信息', false)
  .option('--no-color', '禁用颜色输出')
  .hook('preAction', async (thisCmd) => {
    const opts = thisCmd.opts();
    if (opts.verbose) {
      process.env.VERBOSE = '1';
    }
    if (opts.noColor) {
      chalk.level = 0;
    }
  });

// 打印 banner
printBanner();

// 注册子命令
analyzeCommand(program);
reportCommand(program);
serveCommand(program);
configCommand(program);

// 主命令执行前的全局错误处理
program.configureOutput({
  writeErr: (str) => {
    console.error(chalk.red('错误:') + ' ' + str);
  }
});

// 未知命令处理
program.on('command:*', ([cmd]) => {
  console.error(chalk.red(`未知命令: ${cmd}`));
  console.log(chalk.yellow('使用 --help 查看可用命令'));
  process.exit(1);
});

// 优雅退出
process.on('SIGINT', () => {
  console.log(chalk.yellow('\n\n操作已取消'));
  process.exit(0);
});

process.on('uncaughtException', (err) => {
  console.error(chalk.red('未捕获的异常:'), err.message);
  if (process.env.VERBOSE) {
    console.error(err.stack);
  }
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  console.error(chalk.red('未处理的 Promise 拒绝:'), reason);
  if (process.env.VERBOSE) {
    console.error(reason);
  }
  process.exit(1);
});

// 解析命令行参数
program.parse();