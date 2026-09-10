# 故障排查

## `ModuleNotFoundError: langgraph/sqlmodel/docx`

通常是命令调用了系统 Python 或 Anaconda base。使用：

```powershell
conda run -n ResearchAgent python -c 'import sys; print(sys.executable)'
conda run -n ResearchAgent python -m pip install -r backend/requirements.txt
```

## 前端打开但 API 请求失败

检查后端健康接口和端口，并确保自定义后端端口同步传给前端：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

## 启动时提示端口被占用

启动器不会自动换端口。结束占用进程，或使用[安装与配置文档](SETUP.md#使用自定义端口)中的成对命令。

## MySQL TLS 或密码文件报错

- 确认 `MYSQL_PASSWORD_FILE` 是相对 `backend/` 的路径或有效绝对路径。
- 确认启动用户对密码文件有读取权限。
- 开启 TLS 时确认 `MYSQL_SSL_CA` 存在且与 MySQL Server 证书匹配。
- 只在回环开发环境中临时关闭 TLS，不要把该设置用于远程数据库。

## “来源”看起来有颜色但不能点击

只有蓝色按钮形式的“来源”才包含真实 `document_id/chunk_index`。历史回答中的 `[1, Sec.2.3]`、`[来源 3]` 或粉色 Markdown 代码样式只是普通文本，刷新页面不会自动补齐定位信息；重新提问后生成机器引用即可定位。

## 点击来源后提示原文变化或无法唯一定位

引用定位会校验原文件 MD5。文件被替换、索引被删除或相同文本在文档中重复且旧索引没有偏移信息时，系统会拒绝猜测位置。重新上传/入库并重新提问，生成新的引用映射。

