# LaTeX 文档生成器

本地 Web 应用：输入自然语言需求（可附带上传文件/图片）→ 调用云端免费大模型（默认智谱 GLM）生成 LaTeX →
Tectonic 自动编译 → 编译失败自动修复（最多 3 轮）→ 网页内预览 PDF、一键下载。

**附件支持**：
- `.tex` 源码 → 作为**格式示范**，模型严格模仿其结构、导言区与排版风格
- `.txt` / `.md` → 作为**知识来源**（内容素材与事实依据）
- `.pdf` → 提取前 20 页文本作为知识来源（扫描件无文本层会提示改传图片）
- 图片（png/jpg/webp）→ 调用免费视觉模型识别：同时提取版式格式特征与图中文字/公式内容
- 上传附件后可选择用途：自动判断 / 仅作格式示范 / 仅作知识来源

**PDF 转 LaTeX**：左侧「🔁 PDF 转 LaTeX」上传 PDF → AI 从提取文本近似重建 LaTeX（复杂版式与图片无法完全还原，结果仅供格式参考）→ 自动编译出预览 → 可下载 `.tex`，或点「用作格式示范」直接把它加入下一任务的附件。

**历史记录**：左侧「🕘 历史记录」列出所有历史任务（含转换任务），重启服务后仍在；点击可回看源码与 PDF、直接重新编译；每条可单独删除。

**PDF 转 LaTeX / 历史记录之外**：页面右上角「⏻ 退出服务」可干净停止后台服务（无窗口启动时的退出方式）。

## 环境要求

- Windows + Python 3.10+（已在 3.14 上开发测试）
- 能访问智谱开放平台（生成）与 CTAN 镜像（Tectonic 首次编译下载宏包）

## 首次准备（两步）

1. **放置编译器**：把 `tectonic.exe` 放入项目 `vendor/` 目录。
   （若还没下载：从 [Releases](https://github.com/tectonic-typesetting/tectonic/releases)
   下载 `x86_64-pc-windows-msvc.zip` 解压，或直接运行 `python download_tectonic.py`）
2. **配置 Key**：打开根目录的 `.env`，把 `LLM_API_KEY=` 后面换成你的智谱 API Key
   （在 [open.bigmodel.cn](https://open.bigmodel.cn) 的「API Keys」页面创建）。

## 启动与使用

**方式一（推荐）：桌面快捷方式**——运行一次 `python make_shortcut.py` 生成桌面快捷方式（含图标），
以后双击「LaTeX 文档生成器」即可：**无命令提示符窗口**后台启动服务并打开页面；若服务已在运行则直接打开页面。
停止服务：页面右上角「⏻ 退出服务」按钮。

**方式二：命令行**

```bash
pip install -r requirements.txt   # 仅首次需要
python -m app.main                # 在项目根目录执行（控制台窗口模式，关窗即停）
```

浏览器打开 <http://127.0.0.1:8000>：

1. 选择文档类型（智能判断 / 中文报告 / 英文论文 / 简历 / 信件 / 幻灯片）
2. 填写需求描述，需要时点「添加附件」（或拖拽文件到框内）并选择附件用途
3. 点击「生成 PDF」
4. 页面实时显示附件识别、LaTeX 源码与各阶段进度；完成后自动预览，可下载或复制源码
5. 编译失败时模型会带错误日志自动修复；3 轮后仍失败可手动改源码点「重新编译」
6. 生成成功后也可在「LaTeX 源码」页直接手动修改，点「重新编译」即时更新 PDF 预览

页面顶栏会显示环境自检结果（Key 是否配置、Tectonic 是否就位）。

## 配置项（`.env`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `LLM_API_KEY` | — | 智谱 API Key（必填） |
| `LLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4/` | OpenAI 兼容接口地址，换平台只改这里 |
| `LLM_MODEL` | `glm-4.5-flash` | 模型名，如 `glm-4-flash`（更快）、`glm-4.7-flash`（更强） |
| `LLM_VISION_MODEL` | `glm-4.6v-flash` | 视觉模型（识别上传图片），智谱免费；旧款可用 `glm-4v-flash` |
| `LLM_MAX_TOKENS` | `8192` | 单次生成最大输出 token，长文档可调大 |
| `MAX_FIX_ROUNDS` | `3` | 编译失败自动修复最大轮数 |
| `COMPILE_TIMEOUT` | `180` | 单次编译超时秒数 |
| `MAX_UPLOAD_MB` | `10` | 单个附件大小上限 |
| `HOST` / `PORT` | `127.0.0.1` / `8000` | 监听地址与端口 |

### 更换模型平台

任何 OpenAI 兼容平台都可直接使用，改 `.env` 三项即可，例如硅基流动：

```ini
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_API_KEY=你的Key
LLM_MODEL=Qwen/Qwen2.5-7B-Instruct
```

### 局域网开放（可选）

`.env` 中设 `HOST=0.0.0.0`（或启动时 `python -m uvicorn app.main:app --host 0.0.0.0`），
同网段设备访问 `http://你的IP:8000`；Windows 防火墙首次启动时选择「允许访问」。

## 常见问题

- **首次编译很慢**：Tectonic 需联网下载所用宏包（每个包只下载一次），属正常现象。
- **提示速率限制**：免费档模型并发/频率有限，服务端已按串行排队处理，稍等重试即可。
- **API Key 报错**：确认 Key 复制完整、未过期；修改 `.env` 后需重启服务生效。
- **生成的 PDF 预览空白**：个别浏览器对内嵌 PDF 支持差，直接点「下载 PDF」打开即可。
- **任务取消无响应**：取消仅在生成阶段立即生效；编译阶段需等待当前编译结束。

## 项目结构

```
LaTeX/
├── app/
│   ├── main.py            # FastAPI 入口 + 路由
│   ├── jobs.py            # 串行任务队列
│   ├── core/
│   │   ├── config.py      # .env 配置加载
│   │   ├── prompts.py     # ★ 提示词：系统约束 + 文档骨架 + 修复提示词
│   │   ├── llm_client.py  # OpenAI 兼容流式客户端
│   │   ├── compiler.py    # Tectonic 子进程封装
│   │   ├── error_fixer.py # 编译错误解析
│   │   └── pipeline.py    # 生成→编译→修复循环
│   └── static/            # 前端页面
├── vendor/                # 放置 tectonic.exe
├── workspace/             # 每个任务的 tex/pdf/日志（可随时清理）
├── start_app.bat          # 控制台方式启动（关窗即停，便于看日志）
├── start_app.pyw          # 无窗口启动器（桌面快捷方式指向它）
├── make_shortcut.py       # 生成桌面快捷方式（含图标）
├── download_tectonic.py   # 可选：自动下载 tectonic.exe
├── .env                   # 你的私有配置（不入库）
├── .env.example           # 配置模板
└── requirements.txt
```
