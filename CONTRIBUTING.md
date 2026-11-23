# Contributing

感谢你愿意改进 bmp2dxf！

## 开发环境

```bash
git clone https://github.com/CreationTV/bmp2dxf.git
cd bmp2dxf
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e ".[dev]"
# macOS / Linux
.venv/bin/python -m pip install -e ".[dev]"
```

运行测试：

```bash
python -m pytest -q
```

重新生成演示素材：

```bash
python scripts/make_samples.py
python scripts/make_examples.py
```

## 提交 Issue 时最有帮助的信息

1. 原始图片（可以裁切，但不要加滤镜）；
2. 使用的模式、精度、断线连接等参数；
3. 期望结果与实际结果（截图或 DXF 片段）；
4. 系统 / Python / bmp2dxf 版本。

## Pull Request

- 核心算法（`bmp2dxf/engine/`）请尽量附带一个能复现问题的合成图测试；
- UI 改动请确认桌面与窄屏布局；
- 提交前运行 `python -m pytest -q`；
- 一个 PR 聚焦一件事，便于审查。

## 代码约定

- Python 3.10+，使用类型注解和 `from __future__ import annotations`；
- 核心算法不依赖 GUI/HTTP；
- 新增依赖请说明理由，并优先使用项目已有依赖（numpy / scipy / scikit-image / Pillow / ezdxf）；
- 注释解释“为什么”，而不是重复“做了什么”。
