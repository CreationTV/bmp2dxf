# bmp2dxf v1.1.0

Windows 便携版首发 · 中英文界面切换 · 彩色手绘边界引擎

[![Portable](https://img.shields.io/badge/Windows-portable%20.zip-B5471D.svg)](https://github.com/CreationTV/bmp2dxf/releases/latest)

## 下载 / Download

| 文件 | 说明 |
| --- | --- |
| `bmp2dxf-portable-windows-x64-v1.1.0.zip` | Windows x64 便携版，解压即用，无需安装 Python |
| `SHA256SUMS.txt` | 发布包 SHA-256 校验值 |

解压后双击 **`bmp2dxf.exe`**：本地工作台会在浏览器打开。关闭控制台窗口即可停止服务。
也可以直接在命令行中使用：`bmp2dxf.exe convert samples\mechanical.png -o out\mechanical.dxf`。

> 便携版未做代码签名；首次运行如果 Windows SmartScreen 拦截，请选择「更多信息 → 仍要运行」。

## 本次更新 / What's New

- **Windows 便携版**：PyInstaller one-folder 打包，内置 Python 运行时、依赖与示例图；保留完整 CLI。
- **中英文界面切换**：Web 工作台右上角 `EN / 中文` 按钮，选择会保存在浏览器 localStorage；英文界面覆盖模式、阈值、自动判断理由、警告、样张名与状态提示。
- **彩色边界引擎**：新增 `color` 模式，追踪相邻色块之间的边界，解决彩色平涂手绘、插画、连续色块细节大量丢失的问题；自动模式可识别平坦彩色图。
- **自动模式性能保护**：先用轻量 `probe_color` 判断，避免普通照片走彩色分析而变慢。
- **测试**：104 个自动化用例全部通过；新增彩色边界、中英文静态资源与 Web API 测试。
- **文档**：中文 README 保持默认，新增英文 `README.en.md`，两版可通过顶部语言入口切换。

## 验证 / Verification

- `pytest`: 104 passed
- 便携包：`bmp2dxf.exe --version` → `bmp2dxf 1.1.0`；解压后无需 Python 即可启动 Web 工作台。
- 便携版 Web smoke test: 启动 → `/api/health`（`version: 1.1.0`）→ 样张 API → 上传/转换/下载 DXF → 中英文切换，均通过且无前端报错。
- 便携版 CLI：`mechanical.png` → 26 paths / 171 points / 2031.34 mm（auto centerline）；`color_illustration.png` → 20 paths / 152 points / 1604.39 mm（`--mode color`），DXF 可被 ezdxf 读取。
- 发布资产：`bmp2dxf-portable-windows-x64-v1.1.0.zip` 约 66.4 MiB；解压约 151.2 MiB；SHA-256 `a955dbbc4079ddb945504e1040c7c3c02de741b894f9ece641c5ebf656681067`（同步见 `SHA256SUMS.txt`）。
- 普通黑白样例的 auto 行为与 1.0.0 保持一致；彩色图 auto 正确选择 `color` 模式。

## 已知限制 / Known Limitations

- 当前发布包是 Windows x64，未签名；macOS/Linux 请从源码运行。
- 彩色模式最多量化 12 个颜色区域，适合平涂/色块清晰的手绘图；连续色调照片建议使用中心线/轮廓模式。
- 便携版启动时可能触发杀毒软件首次扫描，后续启动更快。

完整说明见 [README.md](README.md) / [README.en.md](README.en.md)。
