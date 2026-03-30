/**
 * EMR Timestamp Archaeologist - config 命令
 * 管理 API key 等配置，支持加密存储
 */

import { Command } from 'commander';
import chalk from 'chalk';
import crypto from 'crypto';
import fs from 'fs';
import inquirer from 'inquirer';
import os from 'os';
import path from 'path';

// ─────────────────────────────────────────────────────────────
// 配置服务和加密（作为模块导出，供其他 CLI 模块使用）
// ─────────────────────────────────────────────────────────────

export interface AppConfig {
  version: string;
  api: ApiConfig;
  llm: LlmConfig;
  detector: DetectorConfig;
  cache: CacheConfig;
  verbose: boolean;
  log_level: string;
  log_file?: string;
}

export interface ApiConfig {
  provider: 'openai' | 'anthropic';
  api_key: string; // 加密存储
  model: string;
  api_base?: string;
}

export interface LlmConfig {
  enabled: boolean;
  temperature: number;
  max_tokens: number;
  timeout: number;
}

export interface DetectorConfig {
  batch_threshold_seconds: number;
  night_start: number;
  night_end: number;
  min_batch_size: number;
  sequence_rush_minutes: number;
}

export interface CacheConfig {
  enabled: boolean;
  ttl_hours: number;
  max_size_mb: number;
}

const DEFAULT_CONFIG: AppConfig = {
  version: '1.0.0',
  api: {
    provider: 'anthropic',
    api_key: '',
    model: 'claude-sonnet-4-20250514',
  },
  llm: {
    enabled: true,
    temperature: 0.3,
    max_tokens: 4096,
    timeout: 60,
  },
  detector: {
    batch_threshold_seconds: 60,
    night_start: 22,
    night_end: 5,
    min_batch_size: 3,
    sequence_rush_minutes: 5,
  },
  cache: {
    enabled: true,
    ttl_hours: 24,
    max_size_mb: 500,
  },
  verbose: false,
  log_level: 'INFO',
};

// 配置目录和文件
const CONFIG_DIR = path.join(os.homedir(), '.emr-archaeologist');
const CONFIG_FILE = path.join(CONFIG_DIR, 'config.json');
const CACHE_DIR = path.join(CONFIG_DIR, 'cache');
const LOG_DIR = path.join(CONFIG_DIR, 'logs');

/**
 * 生成机器相关的加密 key
 */
function _getEncryptionKey(): Buffer {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
  const machineId = `${os.hostname()}-${os.platform()}-${os.arch()}`;
  const salt = 'emr-archaeologist-v1';
  return crypto.scryptSync(machineId + salt, salt, 32);
}

/**
 * 加密 API key (AES-256-GCM)
 * 格式: iv:authTag:encrypted
 */
export function encryptApiKey(plainKey: string): string {
  const key = _getEncryptionKey();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-gcm', key, iv);
  let encrypted = cipher.update(plainKey, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag();
  return `${iv.toString('hex')}:${authTag.toString('hex')}:${encrypted}`;
}

/**
 * 解密 API key
 */
export function decryptApiKey(encryptedKey: string): string {
  try {
    const key = _getEncryptionKey();
    const parts = encryptedKey.split(':');
    if (parts.length !== 3) return '';
    const iv = Buffer.from(parts[0], 'hex');
    const authTag = Buffer.from(parts[1], 'hex');
    const encrypted = parts[2];
    const decipher = crypto.createDecipheriv('aes-256-gcm', key, iv);
    decipher.setAuthTag(authTag);
    let decrypted = decipher.update(encrypted, 'hex', 'utf8');
    decrypted += decipher.final('utf8');
    return decrypted;
  } catch {
    return '';
  }
}

/**
 * ConfigService 类 - 配置管理核心
 */
export class ConfigService {
  private _config: AppConfig | null = null;

  private _ensureDirs(): void {
    [CONFIG_DIR, CACHE_DIR, LOG_DIR].forEach((dir) => {
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }
    });
  }

  load(): AppConfig {
    this._ensureDirs();
    if (this._config) return this._config;

    if (!fs.existsSync(CONFIG_FILE)) {
      this._config = { ...DEFAULT_CONFIG };
      return this._config;
    }

    try {
      const raw = fs.readFileSync(CONFIG_FILE, 'utf-8');
      const saved = JSON.parse(raw) as AppConfig;

      // 解密 api_key
      if (saved.api?.api_key && saved.api.api_key.includes(':')) {
        saved.api.api_key = decryptApiKey(saved.api.api_key);
      }

      this._config = { ...DEFAULT_CONFIG, ...saved };
    } catch {
      this._config = { ...DEFAULT_CONFIG };
    }

    return this._config;
  }

  save(config?: AppConfig): void {
    this._ensureDirs();
    const toSave = config ? { ...config } : { ...(this._config || DEFAULT_CONFIG) };

    // 加密 api_key 再存储
    if (toSave.api?.api_key) {
      toSave.api.api_key = encryptApiKey(toSave.api.api_key);
    }

    fs.writeFileSync(CONFIG_FILE, JSON.stringify(toSave, null, 2), 'utf-8');
    this._config = config ? { ...config } : this._config;
  }

  get(key: string, defaultValue?: unknown): unknown {
    const config = this.load();
    const parts = key.split('.');
    let value: unknown = config;
    for (const part of parts) {
      if (value && typeof value === 'object' && part in value) {
        value = (value as Record<string, unknown>)[part];
      } else {
        return defaultValue;
      }
    }
    return value;
  }

  set(key: string, value: unknown): void {
    const config = this.load();
    const parts = key.split('.');
    let target: Record<string, unknown> = config as unknown as Record<string, unknown>;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!(parts[i] in target)) target[parts[i]] = {};
      target = target[parts[i]] as Record<string, unknown>;
    }
    target[parts[parts.length - 1]] = value;
    this._config = config;
    this.save(config);
  }

  getCacheDir(): string {
    this._ensureDirs();
    return CACHE_DIR;
  }

  getLogDir(): string {
    this._ensureDirs();
    return LOG_DIR;
  }

  validateApiKey(apiKey?: string, provider?: string): { valid: boolean; message: string } {
    const cfg = this.load();
    const key = apiKey ?? cfg.api.api_key;
    const prov = provider ?? cfg.api.provider;

    if (!key) return { valid: false, message: 'API key 未设置' };

    if (prov === 'anthropic') {
      if (!key.startsWith('sk-ant-')) {
        return { valid: false, message: 'Anthropic API key 应以 sk-ant- 开头' };
      }
    } else if (prov === 'openai') {
      if (!key.startsWith('sk-')) {
        return { valid: false, message: 'OpenAI API key 应以 sk- 开头' };
      }
    }
    return { valid: true, message: 'API key 格式正确' };
  }

  reset(): void {
    this._config = { ...DEFAULT_CONFIG };
    this.save(this._config);
  }
}

// 便捷实例
export const configService = new ConfigService();

// ─────────────────────────────────────────────────────────────
// CLI 命令实现
// ─────────────────────────────────────────────────────────────

function _maskKey(key: string, showChars = 4): string {
  if (!key || key.length <= showChars * 2) return '*'.repeat(key.length || 10);
  return key.slice(0, showChars) + '*'.repeat(Math.min(key.length - showChars * 2, 20)) + key.slice(-showChars);
}

export function configCommand(program: Command): void {
  const cfg = program.command('config').description('查看和管理配置');

  // config show
  cfg.command('show').description('显示当前配置').action(() => {
    const config = configService.load();

    console.log(chalk.bold('\n📋 当前配置:\n'));

    console.log(chalk.cyan('  API 配置:'));
    console.log(`    提供商    : ${config.api.provider}`);
    console.log(`    模型      : ${config.api.model}`);
    console.log(
      `    API Key   : ${config.api.api_key ? chalk.green(_maskKey(config.api.api_key)) : chalk.yellow('(未设置)')}`
    );
    console.log(`    API Base  : ${config.api.api_base || '(默认)'}`);

    console.log(chalk.cyan('\n  LLM 配置:'));
    console.log(`    启用      : ${config.llm.enabled}`);
    console.log(`    温度      : ${config.llm.temperature}`);
    console.log(`    最大 Token: ${config.llm.max_tokens}`);
    console.log(`    超时(s)   : ${config.llm.timeout}`);

    console.log(chalk.cyan('\n  检测器配置:'));
    console.log(`    批处理阈值(s): ${config.detector.batch_threshold_seconds}`);
    console.log(`    夜间时段     : ${config.detector.night_start}:00 - ${config.detector.night_end}:00`);
    console.log(`    最小批大小   : ${config.detector.min_batch_size}`);

    console.log(chalk.cyan('\n  缓存配置:'));
    console.log(`    启用   : ${config.cache.enabled}`);
    console.log(`    TTL(h) : ${config.cache.ttl_hours}`);
    console.log(`    最大MB : ${config.cache.max_size_mb}`);

    console.log(chalk.cyan('\n  目录:'));
    console.log(`    配置目录: ${CONFIG_DIR}`);
    console.log(`    缓存目录: ${CACHE_DIR}`);
    console.log(`    日志目录: ${LOG_DIR}`);

    if (config.api.api_key) {
      const v = configService.validateApiKey();
      console.log(
        chalk.cyan('\n  状态:') +
        `\n    API Key: ${v.valid ? chalk.green('✓ 有效') : chalk.red('✗ ' + v.message)}`
      );
    }

    console.log('');
  });

  // config set
  cfg.command('set')
    .description('设置配置项')
    .argument('<key>', '配置键 (如 api.provider, llm.temperature)')
    .argument('<value>', '配置值')
    .action((key: string, value: string) => {
      const config = configService.load();
      const parts = key.split('.');
      let target: Record<string, unknown> = config as unknown as Record<string, unknown>;

      for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in target)) {
          console.error(chalk.red(`配置路径不存在: ${key}`));
          process.exit(1);
        }
        target = target[parts[i]] as Record<string, unknown>;
      }

      const finalKey = parts[parts.length - 1];
      if (!(finalKey in target)) {
        console.error(chalk.red(`配置项不存在: ${key}`));
        process.exit(1);
      }

      // 类型推断
      const original = target[finalKey];
      let typedValue: unknown = value;
      if (typeof original === 'boolean') {
        typedValue = value.toLowerCase() === 'true' || value === '1';
      } else if (typeof original === 'number') {
        typedValue = parseFloat(value);
        if (isNaN(typedValue as number)) {
          console.error(chalk.red(`无效数字: ${value}`));
          process.exit(1);
        }
      }

      target[finalKey] = typedValue;
      configService.save(config);
      console.log(chalk.green(`\n✅ 已设置 ${key} = ${typedValue}\n`));
    });

  // config get
  cfg.command('get').description('获取配置项').argument('<key>', '配置键').action((key: string) => {
    const value = configService.get(key);
    if (value === undefined) {
      console.error(chalk.red(`配置项不存在: ${key}`));
      process.exit(1);
    }
    if (key.endsWith('.api_key') && typeof value === 'string' && value) {
      console.log(chalk.bold(`\n${key}: `) + chalk.green(_maskKey(value)) + '\n');
    } else {
      console.log(chalk.bold(`\n${key}: `) + `${value}\n`);
    }
  });

  // config init
  cfg.command('init').description('运行配置初始化向导').action(async () => {
    console.log(chalk.cyan('\n🔧 EMR Archaeologist 配置向导\n'));
    console.log(chalk.gray('首次使用需要配置 API key 以启用 LLM 分析功能。\n'));

    const answers = await inquirer.prompt([
      {
        type: 'list',
        name: 'provider',
        message: '选择 LLM 服务提供商:',
        choices: [
          { name: 'Anthropic (Claude)', value: 'anthropic' },
          { name: 'OpenAI (GPT-4)', value: 'openai' },
        ],
        default: 'anthropic',
      },
      {
        type: 'input',
        name: 'apiKey',
        message: '请输入 API Key:',
        validate: (input: string, answers: any) => {
          const result = configService.validateApiKey(input, answers.provider || 'anthropic');
          return result.valid || result.message;
        },
      },
      {
        type: 'input',
        name: 'model',
        message: '请输入模型名称 (直接回车使用默认):',
        default: (answers: any) =>
          answers.provider === 'anthropic' ? 'claude-sonnet-4-20250514' : 'gpt-4o-mini',
      },
      {
        type: 'confirm',
        name: 'llmEnabled',
        message: '是否启用 LLM 分析?',
        default: true,
      },
    ]);

    const config = configService.load();
    config.api.provider = answers.provider;
    config.api.api_key = answers.apiKey;
    config.api.model = answers.model || config.api.model;
    config.llm.enabled = answers.llmEnabled;
    configService.save(config);

    console.log(chalk.green('\n✅ 配置已保存!\n'));
    console.log(chalk.gray(`  提供商: ${config.api.provider}`));
    console.log(chalk.gray(`  模型: ${config.api.model}`));
    console.log(chalk.gray(`  LLM 启用: ${config.llm.enabled}\n`));
  });

  // config reset
  cfg.command('reset').description('重置所有配置为默认值').action(() => {
    console.log(chalk.yellow('\n⚠️  确定要重置所有配置吗? 此操作不可恢复。\n'));

    inquirer
      .prompt([
        {
          type: 'confirm',
          name: 'confirm',
          message: '确认重置?',
          default: false,
        },
      ])
      .then((answers: { confirm: boolean }) => {
        if (answers.confirm) {
          configService.reset();
          console.log(chalk.green('\n✅ 配置已重置为默认值\n'));
        } else {
          console.log(chalk.gray('\n已取消。\n'));
        }
      });
  });
}
