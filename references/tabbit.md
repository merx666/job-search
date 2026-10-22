# 自带的 Tabbit 最小操作说明

此 Skill 不依赖另外安装私人版 Tabbit Skill。需要已安装的 Tabbit 稳定 CLI；宿主若提供更新的官方 Tabbit 技能，优先按其 API 文档操作。

启动器：macOS/Linux `$HOME/.local/bin/tabbit-cli`；Windows `%LOCALAPPDATA%\Tabbit\LocalAgent\bin\tabbit-cli.exe`。可用 `TABBIT_CLI` 指定安装后的稳定启动器，不得直接调用应用包内版本化 runtime。不要读取 endpoint.json、Cookie、令牌或浏览器配置库。

```bash
"$HOME/.local/bin/tabbit-cli" create --task "岗位短名单"
"$HOME/.local/bin/tabbit-cli" nodejs --task "岗位短名单" --request-id inspect-1 --timeout-ms 60000 <<'JS'
await page.goto('https://maimai.cn/', {waitUntil:'domcontentloaded',timeout:25000});
return await tabbit.observe({frames:'none',maxChars:6000});
JS
```

`nodejs` 提供 `page/context/pages()/usePage/tabbit/reportIssue`。常规 Playwright 语义定位可用；先 observe 再定位控件。新程序使用新 request-id；排队/运行中的同一个程序只读原 receipt，不换 ID 重跑。超时 60000–180000ms；本项目设为 60000ms。

必须先读取完整标签清单（truncated 时按 nextCursor 继续）。已存在的平台标签优先使用：`nodejs --task NAME --tab OBSERVED_ID ...`，只读观察而不 goto/reload。只有没有该平台标签才新开页面；claimed 不可绕开。**采集类程序（搜索、翻页、捕获响应）同样优先 `--tab` 复用用户已打开的同平台标签**——平台会把自动化新建的页面在渲染后数秒内置为 about:blank，用户标签不受影响；复用采集后不要 close 该标签。没有现成标签才 `context.newPage()` 开一次性页面：goto 前挂好 response 监听，捕获到响应立即返回并关闭页面，不做长等待；置空前已到达的响应依然有效，不得丢弃。**页面正被平台置空导航时，`response.json()`/`page.evaluate()` 可能永久挂起并把整个程序拖到 60 秒硬期限被杀**——自写程序必须给所有页面内 await 加竞速限时（本项目用 3–8 秒），并对总捕获窗口设上限。

首次创建会返回已有标签清单；用户现有标签须按观察到的 tab ID 明确 acquire，不能接管其他任务的标签。`context.newPage()` 仅创建本任务新页面。`page.goto` 不保证 SPA 内容已载入，使用可见控件/状态等待，最多数秒后报告未知，避免误判空态。

返回 `status=succeeded` 后读取 `result.value`。`queued/running`：

```bash
"$HOME/.local/bin/tabbit-cli" receipt --task "岗位短名单" --request-id inspect-1 --wait-ms 20000
```

资源结果使用 `resource --task NAME --resource ID --offset 0 --max-bytes 32768`，按 `nextOffset` 读取到 `eof`。截断未读完不能认为成功。快照 `snapshotTruncated=true` 时缩小观察范围，资源分页不能恢复被省略的内容。

登录墙用 `reportIssue('AUTHENTICATION_REQUIRED')`；验证/限制用 `reportIssue('SITE_ACCESS_BLOCKED')`，不自动处理验证码。记录 URL，保留页面，执行 `finish` 释放所有权。完成后：

```bash
"$HOME/.local/bin/tabbit-cli" finish --task "岗位短名单"
```

不要使用 `--discard` 关闭用户页面。若结果显示 `forcedCleanup`，不能声称正常释放。浏览器连接受沙箱限制时请求宿主授权；网页权限或未知登录不能通过调试接口规避。

## 模型限流与恢复

默认单 Agent、单浏览器任务、串行平台操作。不要用子 Agent 分平台或另起模型点评岗位。出现 Codex `exceeded retry limit ... 429` 时停止本轮自动调用，保留已完成结果；这不是网站 HTTP 429 的证据。原脚本没有模型 API 客户端，模型 429 可能在宿主回合外发生，不能依赖脚本捕获。

恢复时先读已有 plan/platform-status/raw-jobs/next-actions，保留用户已经确认的平台跳过决定。只读原 receipt；未决请求不能用新 request-id 重跑。程序的 queued/running receipt 等待是在读取结果，不是重新发送搜索请求。

每条提示链接独立排版，例如 `[BOSS直聘](https://www.zhipin.com/)`、`[猎聘](https://www.liepin.com/)`，避免中文括号和整句说明进入 URL。
