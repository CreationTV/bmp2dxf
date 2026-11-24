# bmp2dxf v1.1.1

Windows 便携版修复版 · 防止浏览器缓存旧版 Web UI

[![Portable](https://img.shields.io/badge/Windows-portable%20.zip-B5471D.svg)](https://github.com/CreationTV/bmp2dxf/releases/latest)

## 下载 / Download

| 文件 | 说明 |
| --- | --- |
| `bmp2dxf-portable-windows-x64-v1.1.1.zip` | Windows x64 便携版，解压即用，无需安装 Python |
| `SHA256SUMS.txt` | 发布包 SHA-256 校验值 |

解压后双击 **`bmp2dxf.exe`**：本地工作台会在浏览器打开。关闭控制台窗口即可停止服务。
也可以直接在命令行中使用：`bmp2dxf.exe convert samples\mechanical.png -o out\mechanical.dxf`。

> 便携版未做代码签名；首次运行如果 Windows SmartScreen 拦截，请选择「更多信息 → 仍要运行」。

## 本次修复 / What's Changed

- **Web UI 缓存修复**：静态资源改为 `Cache-Control: no-cache`，并给 CSS/JS 增加版本化查询参数；更新程序后刷新页面即可看到最新工作台，不再被浏览器旧缓存“回滚”到旧界面。
- **界面与功能不变**：仍为复古桌面工作台、中英文切换、四种模式（自动 / 中心线 / 轮廓 / 彩色）、104 个测试覆盖的同一转换引擎。
- **诊断入口**：页面右上角服务状态显示版本号；访问 `/api/health` 可直接确认当前服务版本为 `1.1.1`。

## 验证 / Verification

- `pytest`: 104 passed
- 便携版：`bmp2dxf.exe --version` → `bmp2dxf 1.1.1`
- Web smoke test：启动 → `/api/health`（`version: 1.1.1`）→ 首页加载 → 样张上传/转换/下载 DXF → 中英文切换，均通过且无前端报错。
- 静态资源响应头：`Cache-Control: no-cache`；首页资源 URL 带 `?v=1.1.1`。

### 发布资产 / Release asset

- 文件名：`bmp2dxf-portable-windows-x64-v1.1.1.zip`
- 大小：69,658,748 bytes（约 66.4 MiB）；解压约 158.6 MB（151.2 MiB）
- SHA-256：`c6dfac2911004ef635812b12ded70f86b5e6c545c5cb603505217d9c027dab55`（同步见 `SHA256SUMS.txt`）

## 从旧版本升级 / Upgrading

1. 关闭旧的 `bmp2dxf.exe` 控制台窗口和旧浏览器标签页。
2. 解压新版 zip（建议解压到新文件夹，或先删除旧文件夹再解压）。
3. 双击新版 `bmp2dxf.exe`；如果浏览器仍显示旧页面，按 `Ctrl+F5` 强制刷新一次。

完整说明见 [README.md](README.md) / [README.en.md](README.en.md)。
