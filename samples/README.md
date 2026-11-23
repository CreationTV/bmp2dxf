# 演示图片

这些图片由 [`scripts/make_samples.py`](../scripts/make_samples.py) 生成，覆盖不同难点：

| 文件 | 建议模式 | 难点 |
| --- | --- | --- |
| `mechanical.png` | 中心线 | 24 px 粗线、圆弧、X 交叉、断口、虚线、6 个大小不同的孔 |
| `logo.png` | 轮廓 | 实心圆环、三角形挖孔、粗弧、星形、细线与小点 |
| `text.png` | 轮廓 / 中心线 | 抗锯齿文字、O/R 内孔、尖角 |
| `sketch_scan.jpg` | 自动 / 中心线 | 光照渐变、JPEG 噪点、手绘抖动、断线 |
| `icon.png` | 自动 / 轮廓 | 64 px 小图标，会被自动放大处理 |

在 Web 界面右侧点击缩略图即可直接载入，或使用命令行：

```bash
bmp2dxf convert samples/mechanical.png -o out/mechanical.dxf --preset line --gap 16
bmp2dxf convert samples/logo.png -o out/logo.dxf --preset logo
```
