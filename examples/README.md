# 示例 DXF

这里是对 [`samples/`](../samples/) 中图片运行 bmp2dxf 得到的真实输出，可直接用
AutoCAD / LibreCAD / QCAD / 中望 CAD 打开检查。

| 文件 | 源图 | 模式 | 说明 |
| --- | --- | --- | --- |
| [`mechanical_centerline.dxf`](mechanical_centerline.dxf) | `samples/mechanical.png` | 中心线，精度 82，断线连接 16 px | 粗线单线化、交叉口连续、圆弧/孔洞 |
| [`logo_outline.dxf`](logo_outline.dxf) | `samples/logo.png` | 轮廓，精度 85 | 实心 Logo，保留两个孔洞 |
| [`text_outline.dxf`](text_outline.dxf) | `samples/text.png` | 轮廓，精度 85 | 文字轮廓，保留 O/R 内孔 |
| [`sketch_scan_centerline.dxf`](sketch_scan_centerline.dxf) | `samples/sketch_scan.jpg` | 自动（中心线），精度 80 | 带光照不均与噪点的扫描手绘稿 |

重新生成：

```bash
.venv\Scripts\python scripts\make_examples.py
```

预览叠加图位于 [`docs/images/`](../docs/images/)。
