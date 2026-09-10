# 测试与交付检查

## 后端完整测试

```powershell
Set-Location backend
conda run -n ResearchAgent python -B -m unittest discover -s tests -v
Set-Location ..
```

测试会读取本地数据库配置，但大多数用例使用 mock 或临时目录；不要把测试指向真实 `backend/data/` 做清理。如果 `MYSQL_PASSWORD_FILE` 使用了受限 ACL，应在拥有该文件读取权限的同一 Windows 用户上下文运行测试。

## 前端静态检查与生产构建

```powershell
Set-Location frontend
npm.cmd run lint
npm.cmd run build
Set-Location ..
```

## 浏览器引用回归（可选）

`frontend/tests/browser-regression.mjs` 使用隔离 API、临时合成 PDF/DOCX 和本地 Edge，不会访问真实数据库、模型或用户文档。运行前需要让 Node 能解析 `playwright`。

先启动已构建前端的预览服务器：

```powershell
Set-Location frontend
npm.cmd run build
npm.cmd run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

另开终端，在已安装 Playwright 的 Node 环境中执行：

```powershell
Set-Location frontend
$env:TEST_PYTHON = (conda run -n ResearchAgent python -c 'import sys; print(sys.executable)').Trim()
node tests/browser-regression.mjs
```

默认使用本机 Edge；可通过 `TEST_BROWSER_CHANNEL`、`TEST_BASE_URL` 和 `PLAYWRIGHT_MODULE` 覆盖。

## 代码差异检查

```powershell
git diff --check -- . ':(exclude)backend/data/**' ':(exclude)backend/log/**'
rg -n '^(<<<<<<<|=======|>>>>>>>)' . -g '!frontend/node_modules/**' -g '!frontend/dist/**' -g '!backend/data/**'
```

