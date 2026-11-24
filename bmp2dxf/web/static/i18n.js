/* ==========================================================================
   bmp2dxf Web workbench — English / Chinese UI translation layer.

   The application is authored in Chinese. This file adds an English layer
   without touching the conversion logic in app.js:
   - translates static text nodes and accessible attributes;
   - watches DOM mutations so messages written by app.js are translated too;
   - remembers the original Chinese so switching back is lossless;
   - persists the choice in localStorage and updates <html lang>.
   ========================================================================== */
(function () {
  "use strict";

  var STORAGE_KEY = "bmp2dxf.lang";
  var currentLanguage = "zh";

  var META = {
    zh: {
      title: "工作台 · bmp2dxf",
      description:
        "bmp2dxf 位图转 DXF 矢量图工作台：本地离线转换，适合工程线稿、手绘扫描与图标轮廓。",
      htmlLang: "zh-CN",
      toggleLabel: "EN",
      toggleTitle: "Switch to English"
    },
    en: {
      title: "Workbench · bmp2dxf",
      description:
        "bmp2dxf bitmap-to-DXF vector workbench: fully local and offline, for engineering line art, scanned sketches and icon outlines.",
      htmlLang: "en",
      toggleLabel: "中文",
      toggleTitle: "Switch to Chinese"
    }
  };

  /* Exact strings. Keys are the trimmed Chinese source text. */
  var TEXT = {
    "跳到主内容": "Skip to main content",
    "工作台 · bmp2dxf": "Workbench · bmp2dxf",

    "位图 → 矢量 · 线稿工作台": "Bitmap → vector · line-art workbench",
    "工作台导航": "Workbench navigation",
    "工作台": "Workbench",
    "转换历史": "History",
    "预设库": "Preset library",
    "帮助": "Help",
    "在当前版本中预留": "Reserved for a future version",
    "本地离线 · 检测中": "Local offline · checking",

    "素材与预设": "Source and presets",
    "01 / 素材": "01 / Source",
    "清除": "Clear",
    "选择要转换的图片，或将图片拖拽到这里":
      "Choose an image to convert, or drop it here",
    "拖拽或选择图片": "Drop or choose an image",
    "PNG / JPEG / WebP / BMP / TIFF · 也可以 Ctrl + V":
      "PNG / JPEG / WebP / BMP / TIFF · or Ctrl + V",
    "选择要转换的图片文件": "Choose an image file to convert",
    "已载入": "Loaded",
    "更换": "Replace",
    "图片只在本机转换，不会上传到网络。":
      "Images are converted locally and never uploaded.",

    "02 / 样张": "02 / Samples",
    "载入中": "Loading",
    "正在载入示例图片…": "Loading sample images…",
    "03 / 预设": "03 / Presets",
    "快速套用": "Quick apply",
    "快捷预设": "Quick presets",
    "线稿": "Line art",
    "工程图 · 中心线": "CAD · centerline",
    "手绘扫描": "Sketch scan",
    "抖动笔画 · 连线": "Jitter · join",
    "图标轮廓": "Icon outline",
    "闭合外形 · 保真": "Closed · exact",
    "快速草稿": "Quick draft",
    "低精度 · 速度快": "Low detail · fast",
    "线，继续可以被编辑。": "Lines that stay editable.",
    "中心线 / 轮廓 / 毫米单位": "Centerline / outline / millimetres",

    "04 / 实时预览": "04 / Live preview",
    "实时预览": "Live preview",
    "· 矢量线稿": "· vector line art",
    "预览视图": "Preview view",
    "原图": "Original",
    "矢量": "Vector",
    "叠加": "Overlay",
    "· 位图 → DXF": "· bitmap → DXF",
    "MM / UP · 实时": "MM / UP · live",
    "原图预览": "Original preview",
    "矢量转换结果预览": "Vector conversion preview",
    "还没有图片": "No image yet",
    "从左侧上传或拖入一张线稿，转换结果会实时显示在这里。":
      "Upload or drop line art on the left; the conversion appears here live.",
    "正在转换…": "Converting…",
    "转换失败": "Conversion failed",
    "重试": "Retry",
    "叠加透明度": "Overlay opacity",
    "等待图片": "Waiting for image",
    "中心线": "Centerline",
    "轮廓": "Outline",
    "孔洞": "Hole",

    "06 / 结果": "06 / Results",
    "DXF 就绪": "DXF ready",
    "转换完成后，这里会显示路径数量、节点、线长和耗时。":
      "Path count, nodes, line length and time appear here after conversion.",
    "下载 DXF": "Download DXF",
    "导出 SVG": "Export SVG",
    "自动判断": "Auto decision",
    "检查提示": "Checks",

    "05 / 参数": "05 / Parameters",
    "转换参数": "Conversion parameters",
    "重置": "Reset",
    "模式": "Mode",
    "自动": "Auto",
    "彩色": "Color",
    "根据笔画宽度与填充比例自动选择中心线、轮廓或彩色边界。":
      "Chooses centerline, outline or color boundary from stroke width and fill ratio.",
    "沿笔画中线生成单线路径，适合线稿、扫描草图、CAD 描图。":
      "Follows the middle of each stroke to create single-line paths; ideal for line art, scanned sketches and CAD tracing.",
    "沿墨迹边缘生成闭合轮廓，适合图标、标志、实心色块。":
      "Traces closed contours around ink edges; ideal for icons, logos and solid shapes.",
    "追踪相邻色块之间的边界，适合彩色手绘、插画、平涂色块。":
      "Traces boundaries between adjacent color regions; ideal for color hand drawings, illustrations and flat color blocks.",
    "精度": "Precision",
    "数值越高，保留的细节与节点越多。":
      "Higher values keep more detail and nodes.",
    "断线连接": "Gap closing",
    "自动连接断开的笔画；扫描件可以调大。":
      "Joins broken strokes automatically; increase for scans.",
    "平滑强度": "Smoothing",
    "过高会磨掉尖角与细小细节。":
      "Too much smoothing erases sharp corners and fine detail.",
    "阈值": "Threshold",
    "全局": "Global",
    "自适应": "Adaptive",
    "手动": "Manual",
    "根据背景光照自动选择全局或局部自适应阈值。":
      "Picks a global or local adaptive threshold from background lighting.",
    "全局阈值（Otsu），背景均匀的图片效果最稳。":
      "Global Otsu threshold; most stable on images with an even background.",
    "局部自适应阈值，适合光照不均的扫描件。":
      "Local adaptive threshold; suits scans with uneven lighting.",
    "固定阈值，使用下方滑块手动调节墨迹判定。":
      "Fixed threshold; adjust the ink cutoff with the slider below.",
    "手动阈值": "Manual threshold",
    "低于该灰度的像素视为墨迹；背景发灰时调低，墨迹太浅时调高。":
      "Pixels darker than this value count as ink; lower it for grey backgrounds, raise it for faint ink.",
    "高级参数": "Advanced settings",
    "拐角 · 细节 · 版本": "Corners · detail · version",
    "反相": "Invert",
    "正常": "Normal",
    "正常 = 深色线条 / 浅色背景；反相 = 浅色线条 / 深色背景。":
      "Normal = dark lines on a light background; invert = light lines on a dark background.",
    "决定 DXF 实际尺寸": "Sets the actual DXF size",
    "常用 DPI": "Common DPI",
    "自定义 DPI": "Custom DPI",
    "1 像素 = 25.4 / DPI 毫米；按实际设备设置。":
      "1 pixel = 25.4 / DPI mm; match your output device.",
    "拐角保留阈值": "Corner threshold",
    "夹角大于该值的拐角保留为尖角；调小更硬朗，调大更圆润。":
      "Corners sharper than this angle stay sharp; lower for crisper, higher for smoother.",
    "最小细节": "Minimum detail",
    "忽略小于该尺寸的细节（源图像素）；0 表示自动判断。":
      "Ignore details smaller than this (source pixels); 0 = auto.",
    "DXF 版本": "DXF version",
    "R2000（默认，兼容性最佳）": "R2000 (default, best compatibility)",
    "R12（最老的 CAD 软件）": "R12 (oldest CAD software)",

    "图片不离开这台机器。": "Your image never leaves this machine.",
    "本地离线运行 · 生成毫米单位 DXF":
      "Runs offline · produces millimetre DXF",
    "位图线稿工作台": "Bitmap line-art workbench",
    "Ctrl + V 粘贴图片": "Ctrl + V to paste an image",
    "本地离线": "Local offline",
    "/ 本地离线": "/ Local offline",

    /* app.js dynamic text */
    "服务响应异常": "Unexpected service response",
    "本地服务未连接": "Local service unavailable",
    "版本不可用": "Version unavailable",
    "没有读取到文件，请重新选择图片。":
      "No file was read. Please choose the image again.",
    "这个文件是空的，请选择有效的图片。":
      "This file is empty. Please choose a valid image.",
    "不支持的文件类型。请选择 PNG / JPEG / WebP / BMP / TIFF / GIF 图片。":
      "Unsupported file type. Choose a PNG / JPEG / WebP / BMP / TIFF / GIF image.",
    "无法读取文件": "Could not read the file",
    "浏览器无法解码该图片": "The browser could not decode this image",
    "图片数据为空": "Image data is empty",
    "已选择图片，准备转换…": "Image selected; ready to convert…",
    "浏览器无法直接预览该格式，但转换可以正常进行；完成后请切换到「矢量」标签查看。":
      "The browser cannot preview this format, but conversion still works. Check the Vector tab when it finishes.",
    "未知错误": "Unknown error",
    "尺寸将在转换后显示": "Dimensions appear after conversion",
    "所有转换只在本机服务中完成，不会上传到网络。":
      "All conversion runs in the local service; nothing is uploaded.",
    "已清除图片": "Image cleared",
    "已恢复默认参数": "Default settings restored",
    "网络错误": "Network error",
    "正在重新转换…": "Re-converting…",
    "转换中…": "Converting…",
    "正在转换图片": "Converting image",
    "该格式无法在浏览器中直接预览":
      "This format cannot be previewed in the browser",
    "转换仍会正常进行，完成后切换到「矢量」标签即可查看结果。":
      "Conversion still runs normally; open the Vector tab when done.",
    "正在生成矢量预览": "Generating vector preview",
    "转换完成后会自动显示在这里。":
      "It appears here automatically when conversion finishes.",
    "暂无预览": "No preview yet",
    "切换到「矢量」或「叠加」标签查看转换结果。":
      "Switch to Vector or Overlay to inspect the result.",
    "示例列表加载失败": "Could not load the sample list",
    "示例列表暂时不可用，请确认本地服务正在运行。":
      "Samples are unavailable right now; make sure the local service is running.",
    "samples/ 目录中还没有示例图片。": "No sample images in samples/ yet.",
    "SVG 解析失败": "SVG parsing failed",
    "矢量结果预览": "Vector result preview",

    /* stats labels */
    "路径数": "Paths",
    "节点数": "Nodes",
    "闭合路径": "Closed paths",
    "线长": "Length",
    "耗时": "Time",
    "工作分辨率": "Work size",

    /* sample names */
    "机械图": "CAD",
    "标志": "Logo",
    "文字": "Text",
    "扫描": "Scan",
    "图标": "Icon",

    /* engine auto_reason / warnings */
    "空图像。": "Empty image.",
    "彩色模式需要彩色图片；已回退到轮廓模式。":
      "Color mode needs a color image; falling back to outline mode.",
    "手动选择彩色边界模式。": "color boundary mode selected manually.",
    "手动选择模式。": "Mode selected manually.",
    "检测为线条/均匀笔画图形，自动使用中心线模式：粗线只生成一根线。":
      "Detected line art / uniform strokes; using centerline mode so thick strokes become one line.",
    "图像内容很少，默认使用中心线模式。":
      "Very little content; using centerline mode by default.",
    "使用手动阈值。": "Manual threshold.",
    "背景较均匀，自动使用 Otsu 全局阈值。":
      "Even background; using Otsu global threshold.",
    "阈值模式为手动但未提供数值，回退到 Otsu。":
      "Manual threshold requested without a value; falling back to Otsu.",
    "图像不是明显的彩色平涂画面；彩色模式会直接追踪颜色区域边界，连续色调照片可能产生较多碎线。":
      "This does not look like flat color artwork; Color mode traces every color boundary and may create many small fragments on photos.",
    "未生成任何矢量路径；请尝试调整精度、阈值或模式。":
      "No vector paths were generated; try adjusting precision, threshold or mode.",
    "空白图像，没有可转换的内容。":
      "Blank image; there is nothing to convert.",
    "没有提取到中心线；请尝试调整阈值或使用轮廓模式。":
      "No centerlines were found; try adjusting the threshold or use outline mode.",
    "提取到的线条都小于最小细节尺寸；请提高精度或降低最小细节。":
      "All extracted lines are below the minimum detail size; raise precision or lower minimum detail.",
    "未生成有效中心线，请尝试降低阈值/提高精度。":
      "No valid centerlines were generated; try a lower threshold or higher precision.",
    "没有找到可转换的轮廓。": "No convertible outlines were found.",
    "轮廓都小于最小细节尺寸；请提高精度或降低最小细节。":
      "All outlines are below the minimum detail size; raise precision or lower minimum detail.",
    "没有可用的彩色数据；已回退到轮廓模式。":
      "No usable color data; falling back to outline mode.",
    "图像几乎是单色，未找到颜色区域边界。":
      "The image is almost monochrome; no color boundaries were found.",
    "没有找到彩色区域边界；请尝试提高精度或改用其他模式。":
      "No color boundaries were found; try higher precision or another mode.",
    "这张图片没有可用的颜色信息（灰度/16 位/浮点图），彩色模式已回退到轮廓模式。":
      "This image has no color information (grayscale, 16-bit or float image), so Color mode fell back to outline mode.",
    "检测到动图，只转换第一帧。": "Animated image detected; only the first frame is converted.",
    "几乎没有检测到前景线条：请尝试降低阈值、勾选/取消「反相」，或选择局部自适应阈值。":
      "Almost no foreground lines were detected; try a lower threshold, toggle Invert, or use adaptive thresholding.",
    "前景几乎覆盖整张图片，可能背景判断反了：请尝试切换「反相」或调整阈值。":
      "Foreground covers almost the whole image, so the background may be inverted; try Invert or adjust the threshold.",
    "这似乎是一张连续色调照片而非线稿；转换结果可能只是一些色块轮廓。对照片建议先做描线/二值化预处理。":
      "This looks like a continuous-tone photo rather than line art; the result may only contain block outlines. Pre-process photos with tracing or binarisation first.",

    /* server messages */
    "服务器内部错误，请查看控制台日志。":
      "Internal server error; check the console log.",
    "图片过大，转换时内存不足，请先缩小图片。":
      "The image is too large and conversion ran out of memory; please resize it first.",
    "转换过程中出现内部错误，请查看控制台日志。":
      "An internal error occurred during conversion; check the console log.",
    "图片 data URL 格式不正确，应为 base64 编码。":
      "The image data URL is malformed; expected base64 encoding.",
    "图片 base64 数据为空。": "The image base64 data is empty.",
    "图片 base64 数据无效，无法解码。":
      "The image base64 data is invalid and could not be decoded.",
    "图片 base64 解码后为空。": "The decoded image is empty.",
    "图片文件过大（解码后上限约 48 MB），请先压缩或缩小图片。":
      "The decoded image is too large (about 48 MB limit); compress or resize it first.",
    "请求体过大（上限约 64 MB），请先压缩或缩小图片。":
      "The request body is too large (about 64 MB limit); compress or resize the image first.",
    "请求体为空。": "The request body is empty.",
    "请求体读取不完整。": "The request body was not read completely.",
    "请求体不是有效的 JSON。": "The request body is not valid JSON.",
    "请求体必须是 JSON 对象。": "The request body must be a JSON object.",
    "缺少 image_base64 字段（图片的 base64 数据）。":
      "The image_base64 field is missing.",
    "options 字段必须是 JSON 对象。":
      "The options field must be a JSON object.",
    "图片内容为空": "The image is empty",
    "图片尺寸无效": "Invalid image dimensions",
    "图片像素超过 1.2 亿，请先缩小后再转换":
      "The image exceeds 120 megapixels; please resize it before converting.",
    "转换结果不存在或已过期，请重新转换后再下载。":
      "The conversion result is missing or expired; convert again before downloading."
  };

  /* Messages with numbers or paths. */
  var PATTERNS = [
    {
      re: /^(\d+) · (自动|全局|自适应|手动)$/,
      en: function (m) {
        var methods = {
          "自动": "Auto",
          "全局": "Global",
          "自适应": "Adaptive",
          "手动": "Manual"
        };
        return m[1] + " · " + (methods[m[2]] || m[2]);
      }
    },
    {
      re: /^服务已就绪 · v(.+)$/,
      en: function (m) { return "Service ready · v" + m[1]; }
    },
    {
      re: /^已更新 · (\d+) ms$/,
      en: function (m) { return "Updated · " + m[1] + " ms"; }
    },
    {
      re: /^图片较大（(.+)），转换可能需要几秒钟。$/,
      en: function (m) {
        return "Large image (" + m[1] + "); conversion may take a few seconds.";
      }
    },
    {
      re: /^图片文件过大（(.+)）。为保证浏览器与服务性能，请先压缩到 36 MB 以内。$/,
      en: function (m) {
        return (
          "Image file is too large (" +
          m[1] +
          "). Compress it below 36 MB for browser and service performance."
        );
      }
    },
    {
      re: /^转换失败（HTTP (\d+)）。$/,
      en: function (m) { return "Conversion failed (HTTP " + m[1] + ")."; }
    },
    {
      re: /^无法连接本地服务（(.+)）。请确认启动窗口仍在运行。$/,
      en: function (m) {
        return (
          "Cannot reach the local service (" +
          m[1] +
          "). Make sure the launch window is still running."
        );
      }
    },
    {
      re: /^转换完成：共 (\d+) 条路径，(\d+) 个节点$/,
      en: function (m) {
        return "Conversion complete: " + m[1] + " paths, " + m[2] + " nodes";
      }
    },
    {
      re: /^已应用预设：(.+)$/,
      en: function (m) { return "Preset applied: " + m[1]; }
    },
    {
      re: /^读取图片失败：(.+)$/,
      en: function (m) { return "Could not read image: " + m[1]; }
    },
    {
      re: /^加载示例失败：(.+)$/,
      en: function (m) { return "Could not load sample: " + m[1]; }
    },
    {
      re: /^(\d+) 个$/,
      en: function (m) { return m[1]; }
    },
    {
      re: /^参数错误：(.+)$/,
      en: function (m) { return "Invalid parameter: " + m[1]; }
    },
    {
      re: /^转换失败：(.+)$/,
      en: function (m) { return "Conversion failed: " + m[1]; }
    },
    {
      re: /^图片转换失败：(.+)$/,
      en: function (m) { return "Image conversion failed: " + m[1]; }
    },
    {
      re: /^无法识别的图片格式，支持：(.+)$/,
      en: function (m) { return "Unsupported image format; supported: " + m[1]; }
    },
    {
      re: /^检测到较大比例的实心填充区域（约 (\d+)% 的墨迹面积），自动使用轮廓模式以完整保留外形和细节。$/,
      en: function (m) {
        return (
          "Detected a large share of solid fill (about " +
          m[1] +
          "% of ink area); using outline mode to preserve shapes and details."
        );
      }
    },
    {
      re: /^检测到 (\d+)% 的墨迹属于实心填充区域；中心线模式会沿实心块生成骨架线，若想保留外形轮廓请切换为「轮廓」模式。$/,
      en: function (m) {
        return (
          "About " +
          m[1] +
          "% of the ink is solid fill; centerline mode will trace the skeleton of thick blocks. Switch to Outline mode to keep the silhouette."
        );
      }
    },
    {
      re: /^图片已缩放至 (\d+)×(\d+) 进行矢量化（精度 (\d+)，提高精度可保留更多细节）。$/,
      en: function (m) {
        return (
          "Image resized to " +
          m[1] +
          "×" +
          m[2] +
          " for vectorisation (precision " +
          m[3] +
          "; raise precision for more detail)."
        );
      }
    },
    {
      re: /^检测到背景光照不均（亮度起伏 (\d+)\/255），自动使用局部自适应阈值。$/,
      en: function (m) {
        return (
          "Uneven background lighting detected (brightness range " +
          m[1] +
          "/255); using local adaptive thresholding."
        );
      }
    },
    {
      re: /^检测到彩色平涂画面（彩色像素 (\d+)%，局部平坦度 (\d+)%，填充区域 (\d+)%），自动使用彩色边界模式。$/,
      en: function (m) {
        return (
          "Detected flat color artwork (color pixels " +
          m[1] +
          "%, local flatness " +
          m[2] +
          "%, filled areas " +
          m[3] +
          "%); using color-boundary mode."
        );
      }
    },
    {
      re: /^机械图( · .*)?$/,
      en: function (m) { return "CAD" + (m[1] || ""); }
    },
    {
      re: /^标志( · .*)?$/,
      en: function (m) { return "Logo" + (m[1] || ""); }
    },
    {
      re: /^文字( · .*)?$/,
      en: function (m) { return "Text" + (m[1] || ""); }
    },
    {
      re: /^扫描( · .*)?$/,
      en: function (m) { return "Scan" + (m[1] || ""); }
    },
    {
      re: /^图标( · .*)?$/,
      en: function (m) { return "Icon" + (m[1] || ""); }
    }
  ];

  var ATTRIBUTES = ["title", "aria-label", "alt", "placeholder"];
  var SKIP_TAGS = { SCRIPT: true, STYLE: true, NOSCRIPT: true, TEMPLATE: true };
  var observer = null;
  var toggle = null;
  var toggleLabel = null;

  function hasCJK(value) {
    return /[\u3400-\u9fff]/.test(String(value || ""));
  }

  function trimKey(value) {
    return String(value || "").trim();
  }

  function preserveOuterWhitespace(original, translated) {
    var leading = String(original).match(/^\s*/)[0];
    var trailing = String(original).match(/\s*$/)[0];
    return leading + translated + trailing;
  }

  function translateKey(key) {
    if (!key) {
      return null;
    }
    if (Object.prototype.hasOwnProperty.call(TEXT, key)) {
      return TEXT[key];
    }
    for (var i = 0; i < PATTERNS.length; i += 1) {
      var match = key.match(PATTERNS[i].re);
      if (match) {
        try {
          return PATTERNS[i].en(match);
        } catch (error) {
          return null;
        }
      }
    }
    return null;
  }

  function isSkipped(element) {
    if (!element) {
      return false;
    }
    if (element.id === "langToggle" || element.closest("#langToggle")) {
      return true;
    }
    var tag = element.tagName ? element.tagName.toUpperCase() : "";
    return !!SKIP_TAGS[tag];
  }

  function translateTextNode(node) {
    var value = node.nodeValue;
    if (!value || !hasCJK(value)) {
      return;
    }
    if (isSkipped(node.parentElement)) {
      return;
    }
    if (node.__i18nZh === undefined || value !== node.__i18nApplied) {
      node.__i18nZh = value;
    }
    var translated = translateKey(trimKey(node.__i18nZh));
    if (translated === null) {
      return;
    }
    node.nodeValue = preserveOuterWhitespace(node.__i18nZh, translated);
    node.__i18nApplied = node.nodeValue;
  }

  function translateElementAttribute(element, attribute) {
    var value = element.getAttribute(attribute);
    if (!value || !hasCJK(value) || isSkipped(element)) {
      return;
    }
    if (!element.__i18nAttrs) {
      element.__i18nAttrs = Object.create(null);
      element.__i18nAttrsApplied = Object.create(null);
    }
    var cache = element.__i18nAttrs;
    var applied = element.__i18nAttrsApplied;
    if (cache[attribute] === undefined || value !== applied[attribute]) {
      cache[attribute] = value;
    }
    var translated = translateKey(trimKey(cache[attribute]));
    if (translated === null) {
      return;
    }
    element.setAttribute(attribute, translated);
    applied[attribute] = translated;
  }

  function translateElementAttributes(element) {
    for (var i = 0; i < ATTRIBUTES.length; i += 1) {
      translateElementAttribute(element, ATTRIBUTES[i]);
    }
  }

  function walkForEnglish(rootNode) {
    if (!rootNode) {
      return;
    }
    if (rootNode.nodeType === Node.TEXT_NODE) {
      translateTextNode(rootNode);
      return;
    }
    if (rootNode.nodeType !== Node.ELEMENT_NODE && rootNode.nodeType !== Node.DOCUMENT_NODE) {
      return;
    }
    if (rootNode.nodeType === Node.ELEMENT_NODE) {
      translateElementAttributes(rootNode);
    }
    var Walker = document.createTreeWalker(
      rootNode,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          if (node.nodeType === Node.ELEMENT_NODE && isSkipped(node)) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    var node = Walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        translateTextNode(node);
      } else if (node.nodeType === Node.ELEMENT_NODE) {
        translateElementAttributes(node);
      }
      node = Walker.nextNode();
    }
  }

  function restoreChinese(rootNode) {
    if (!rootNode) {
      return;
    }
    if (rootNode.nodeType === Node.TEXT_NODE) {
      if (rootNode.__i18nZh !== undefined) {
        rootNode.nodeValue = rootNode.__i18nZh;
      }
      return;
    }
    if (rootNode.nodeType !== Node.ELEMENT_NODE && rootNode.nodeType !== Node.DOCUMENT_NODE) {
      return;
    }
    if (rootNode.nodeType === Node.ELEMENT_NODE && rootNode.__i18nAttrs) {
      var attributes = Object.keys(rootNode.__i18nAttrs);
      for (var i = 0; i < attributes.length; i += 1) {
        rootNode.setAttribute(attributes[i], rootNode.__i18nAttrs[attributes[i]]);
      }
    }
    var elements = rootNode.querySelectorAll("*");
    for (var j = 0; j < elements.length; j += 1) {
      var element = elements[j];
      if (element.__i18nAttrs) {
        var keys = Object.keys(element.__i18nAttrs);
        for (var k = 0; k < keys.length; k += 1) {
          element.setAttribute(keys[k], element.__i18nAttrs[keys[k]]);
        }
      }
    }
    var Walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT, null);
    var node = Walker.nextNode();
    while (node) {
      if (node.__i18nZh !== undefined) {
        node.nodeValue = node.__i18nZh;
      }
      node = Walker.nextNode();
    }
  }

  function updateMeta(language) {
    var meta = META[language];
    document.documentElement.lang = meta.htmlLang;
    document.title = meta.title;
    var description = document.querySelector('meta[name="description"]');
    if (description) {
      description.setAttribute("content", meta.description);
    }
    if (toggle) {
      toggle.setAttribute("title", meta.toggleTitle);
      toggle.setAttribute("aria-label", meta.toggleTitle);
    }
    if (toggleLabel) {
      toggleLabel.textContent = meta.toggleLabel;
    }
  }

  function setLanguage(language, persist) {
    var next = language === "en" ? "en" : "zh";
    if (next === "en") {
      walkForEnglish(document.body);
    } else {
      restoreChinese(document.body);
    }
    currentLanguage = next;
    updateMeta(next);
    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, next);
      } catch (error) {
        /* Private mode or blocked storage: the toggle still works for this page. */
      }
    }
  }

  function storedLanguage() {
    try {
      var value = window.localStorage.getItem(STORAGE_KEY);
      return value === "en" ? "en" : "zh";
    } catch (error) {
      return "zh";
    }
  }

  function handleMutations(mutations) {
    if (currentLanguage !== "en") {
      return;
    }
    for (var i = 0; i < mutations.length; i += 1) {
      var mutation = mutations[i];
      if (mutation.type === "characterData") {
        translateTextNode(mutation.target);
      } else if (mutation.type === "childList") {
        for (var j = 0; j < mutation.addedNodes.length; j += 1) {
          walkForEnglish(mutation.addedNodes[j]);
        }
      } else if (mutation.type === "attributes") {
        translateElementAttribute(mutation.target, mutation.attributeName);
      }
    }
  }

  function startObserver() {
    if (observer || typeof MutationObserver === "undefined") {
      return;
    }
    observer = new MutationObserver(handleMutations);
    observer.observe(document.body, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRIBUTES
    });
  }

  function initI18n() {
    toggle = document.getElementById("langToggle");
    toggleLabel = document.getElementById("langToggleLabel");
    var language = storedLanguage();
    if (language === "en") {
      setLanguage("en", false);
    } else {
      updateMeta("zh");
    }
    startObserver();
    if (toggle) {
      toggle.addEventListener("click", function () {
        setLanguage(currentLanguage === "en" ? "zh" : "en", true);
      });
    }
  }

  /* The script is deferred: the body is parsed by the time it runs. */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initI18n);
  } else {
    initI18n();
  }
})();

