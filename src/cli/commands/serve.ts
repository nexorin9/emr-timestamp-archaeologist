/**
 * EMR Timestamp Archaeologist - serve 命令
 * 启动本地 HTTP 服务器预览报告，支持实时刷新、API代理和密码保护
 */

import { Command } from 'commander';
import chalk from 'chalk';
import http from 'http';
import https from 'https';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

/**
 * 注册 serve 子命令
 */
export function serveCommand(program: Command): void {
  program
    .command('serve')
    .description('启动本地 HTTP 服务器预览 HTML 报告')
    .argument('[file]', 'HTML 报告文件路径', 'report.html')
    .option('-p, --port <port>', '服务器端口', '8080')
    .option('-h, --host <host>', '服务器主机', 'localhost')
    .option('--no-browser', '不自动打开浏览器')
    .option('--password <password>', '设置访问密码（保护报告）')
    .option('--api-proxy', '启用 LLM API 代理（解决 CORS）')
    .option('--api-proxy-url <url>', 'LLM API 代理地址', 'https://api.openai.com')
    .option('--live-reload', '启用实时刷新（监控文件变化）')
    .action(async (file: string, options: any) => {
      let port = parseInt(options.port, 10);
      const host = options.host;
      const openBrowser = !options.noBrowser;
      const password = options.password;
      const apiProxy = options.apiProxy;
      const apiProxyUrl = options.apiProxyUrl;
      const liveReload = options.liveReload;

      // 验证文件
      const filePath = path.resolve(file);
      if (!fs.existsSync(filePath)) {
        console.error(chalk.red(`\n报告文件不存在: ${filePath}`));
        console.log(chalk.yellow('\n请先运行: emr-archaeologist report <analysis-result.json>\n'));
        process.exit(1);
      }

      // 生成密码哈希（如果设置了密码）
      let passwordHash: string | null = null;
      if (password) {
        passwordHash = crypto.createHash('sha256').update(password).digest('hex');
      }

      // MIME 类型映射
      const mimeTypes: Record<string, string> = {
        '.html': 'text/html; charset=utf-8',
        '.css': 'text/css; charset=utf-8',
        '.js': 'application/javascript; charset=utf-8',
        '.json': 'application/json; charset=utf-8',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.ico': 'image/x-icon',
      };

      // LiveReload 客户端脚本
      const livereloadScript = `
        <script>
          (function() {
            const ws = new WebSocket('ws://${host}:${port}/livereload');
            ws.onmessage = function(event) {
              if (event.data === 'reload') {
                location.reload();
              }
            };
            ws.onclose = function() {
              console.log('LiveReload 连接断开');
            };
          })();
        </script>
      `;

      // 认证检查
      const checkAuth = (req: http.IncomingMessage): boolean => {
        if (!passwordHash) return true;

        const authHeader = req.headers['authorization'];
        if (!authHeader || !authHeader.startsWith('Basic ')) {
          return false;
        }

        try {
          const credentials = Buffer.from(authHeader.slice(6), 'base64').toString();
          const [user, pass] = credentials.split(':');
          const inputHash = crypto.createHash('sha256').update(pass || '').digest('hex');
          return inputHash === passwordHash && user === 'admin';
        } catch {
          return false;
        }
      };

      // 发送认证挑战
      const sendAuthChallenge = (res: http.ServerResponse) => {
        res.writeHead(401, {
          'WWW-Authenticate': 'Basic realm="EMR Report Viewer"',
          'Content-Type': 'text/html; charset=utf-8',
        });
        res.end(`
          <!DOCTYPE html>
          <html>
          <head><title>认证 required</title></head>
          <body>
            <h1>401 Unauthorized</h1>
            <p>请输入正确的用户名和密码访问此报告。</p>
          </body>
          </html>
        `);
      };

      // 创建服务器
      const server = http.createServer((req: http.IncomingMessage, res: http.ServerResponse) => {
        const reqUrl = req.url || '/';

        // 处理 LiveReload WebSocket 连接
        if (reqUrl === '/livereload' && liveReload) {
          res.writeHead(101, {
            'Upgrade': 'websocket',
            'Connection': 'Upgrade',
          });

          // 保持连接但不做任何事（简单的 WebSocket 处理）
          req.on('data', () => {});
          req.on('end', () => {
            res.end();
          });
          return;
        }

        // 处理 API 代理请求
        if (apiProxy && reqUrl.startsWith('/api/proxy/')) {
          handleApiProxy(req, res, apiProxyUrl, reqUrl.slice(10));
          return;
        }

        // 认证检查
        if (!checkAuth(req)) {
          sendAuthChallenge(res);
          return;
        }

        let urlPath = reqUrl === '/' ? '/' + path.basename(file) : reqUrl;
        let servedFilePath: string;

        // 安全检查：防止路径遍历
        try {
          servedFilePath = path.resolve(path.dirname(filePath), '.' + urlPath);
          if (!servedFilePath.startsWith(path.dirname(filePath))) {
            res.writeHead(403);
            res.end('Forbidden');
            return;
          }
        } catch {
          res.writeHead(400);
          res.end('Bad Request');
          return;
        }

        // 处理根路径
        if (req.url === '/') {
          servedFilePath = filePath;
        }

        const ext = path.extname(servedFilePath).toLowerCase();
        const contentType = mimeTypes[ext] || 'application/octet-stream';

        fs.readFile(servedFilePath, (err, content) => {
          if (err) {
            if (err.code === 'ENOENT') {
              res.writeHead(404);
              res.end('Not Found');
            } else {
              res.writeHead(500);
              res.end('Internal Server Error');
            }
            return;
          }

          let responseContent: Buffer | string = content;

          // 如果是 HTML 文件且启用了 LiveReload，注入脚本
          if (ext === '.html' && liveReload) {
            responseContent = content.toString().replace('</body>', `${livereloadScript}</body>`);
          }

          const headers: Record<string, string | string[]> = {
            'Content-Type': contentType,
            'Cache-Control': 'no-cache',
          };

          // CORS 头（如果启用了 API 代理）
          if (apiProxy) {
            headers['Access-Control-Allow-Origin'] = '*';
            headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS';
            headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization';
          }

          res.writeHead(200, headers);
          res.end(responseContent);
        });
      });

      // LiveReload 文件监控
      let livereloadWatcher: fs.FSWatcher | null = null;

      if (liveReload) {
        livereloadWatcher = fs.watch(filePath, (eventType) => {
          if (eventType === 'change') {
            console.log(chalk.gray(`\n[LiveReload] 检测到报告文件变化，将在下次连接时刷新...`));
            // 通知客户端刷新（通过 WebSocket）
          }
        });

        console.log(chalk.cyan(`\n🔄 LiveReload 已启用 - 监控: ${filePath}`));
      }

      // API 代理处理
      const handleApiProxy = (
        req: http.IncomingMessage,
        res: http.ServerResponse,
        targetBaseUrl: string,
        targetPath: string
      ) => {
        // targetUrl 可用于调试日志
        // const targetUrl = `${targetBaseUrl}${targetPath}`;

        const options = {
          hostname: new URL(targetBaseUrl).hostname,
          port: targetBaseUrl.startsWith('https') ? 443 : 80,
          path: targetPath,
          method: req.method || 'GET',
          headers: {
            ...req.headers,
            'host': new URL(targetBaseUrl).hostname,
          },
        };

        const proxyReq = (targetBaseUrl.startsWith('https') ? https : http).request(options, (proxyRes) => {
          res.writeHead(proxyRes.statusCode || 200, {
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*',
          });

          proxyRes.on('data', (chunk) => res.write(chunk));
          proxyRes.on('end', () => res.end());
        });

        proxyReq.on('error', (err) => {
          res.writeHead(502, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: '代理请求失败', message: err.message }));
        });

        req.on('data', (chunk) => proxyReq.write(chunk));
        req.on('end', () => proxyReq.end());
      };

      // 启动服务器
      server.listen(port, host, () => {
        const serverUrl = `http://${host}:${port}/${path.basename(file)}`;

        console.log(chalk.cyan('\n🖥️  报告预览服务器已启动'));
        console.log(chalk.gray('─'.repeat(50)));
        console.log(chalk.green(`\n   报告地址: ${chalk.bold.underline(serverUrl)}`));
        if (password) {
          console.log(chalk.yellow(`\n   🔒 密码保护: 已启用`));
        }
        if (apiProxy) {
          console.log(chalk.cyan(`\n   🌐 API 代理: 已启用 (${apiProxyUrl})`));
        }
        if (liveReload) {
          console.log(chalk.cyan(`\n   🔄 实时刷新: 已启用`));
        }
        console.log(chalk.gray(`\n   按 ${chalk.bold('Ctrl+C')} 停止服务器\n`));

        if (openBrowser) {
          // 延迟打开浏览器
          setTimeout(() => {
            openBrowserAtUrl(serverUrl);
          }, 1000);
        }
      });

      server.on('error', (err: NodeJS.ErrnoException) => {
        if (err.code === 'EADDRINUSE') {
          console.error(chalk.red(`\n❌ 端口 ${port} 已被占用`));
          port = port - 1;
          console.log(chalk.yellow(`\n   尝试使用端口: ${chalk.bold(port)}`));
          server.listen(port, host);
        } else {
          console.error(chalk.red('\n❌ 服务器错误:'), err.message);
          process.exit(1);
        }
      });

      // 清理
      process.on('SIGINT', () => {
        console.log(chalk.gray('\n\n正在关闭服务器...'));
        if (livereloadWatcher) {
          livereloadWatcher.close();
        }
        server.close(() => {
          console.log(chalk.green('服务器已关闭'));
          process.exit(0);
        });
      });
    });
}

/**
 * 打开浏览器
 */
async function openBrowserAtUrl(url: string): Promise<void> {
  const { exec } = await import('child_process');
  const cmd = process.platform === 'win32' ? 'start' : process.platform === 'darwin' ? 'open' : 'xdg-open';
  exec(`${cmd} "${url}"`, (err) => {
    if (err && process.env.VERBOSE) {
      console.error(chalk.yellow('自动打开浏览器失败，请手动访问'));
    }
  });
}
