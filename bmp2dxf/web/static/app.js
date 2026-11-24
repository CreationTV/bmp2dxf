/* ==========================================================================
   bmp2dxf 本地 Web 工作台 — 前端逻辑
   无框架、无外部依赖，所有转换都发送到本机运行的 Python 服务。
   ========================================================================== */
(function () {
  "use strict";

  /* ---------- 常量 ---------- */
  var DEFAULT_OPTIONS = {
    mode: "auto",
    precision: 70,
    threshold_method: "auto",
    threshold: 128,
    invert: "auto",
    gap_close: 4,
    smoothing: 55,
    corner_angle: 100,
    min_detail: 0,
    dpi: 96,
    dxf_version: "R2000"
  };

  var PRESETS = {
    line: {
      label: "线稿",
      options: {
        mode: "centerline",
        precision: 78,
        gap_close: 5,
        smoothing: 50,
        threshold_method: "auto"
      }
    },
    sketch: {
      label: "手绘扫描",
      options: {
        mode: "centerline",
        precision: 66,
        gap_close: 8,
        smoothing: 68,
        threshold_method: "auto"
      }
    },
    logo: {
      label: "图标轮廓",
      options: {
        mode: "outline",
        precision: 84,
        gap_close: 2,
        smoothing: 45,
        threshold_method: "otsu"
      }
    },
    draft: {
      label: "快速草稿",
      options: {
        mode: "centerline",
        precision: 35,
        gap_close: 10,
        smoothing: 85,
        threshold_method: "auto"
      }
    }
  };

  var MODE_TEXT = { auto: "自动", centerline: "中心线", outline: "轮廓", color: "彩色" };
  var MODE_DESCRIPTION = {
    auto: "根据笔画宽度与填充比例自动选择中心线、轮廓或彩色边界。",
    centerline: "沿笔画中线生成单线路径，适合线稿、扫描草图、CAD 描图。",
    outline: "沿墨迹边缘生成闭合轮廓，适合图标、标志、实心色块。",
    color: "追踪相邻色块之间的边界，适合彩色手绘、插画、平涂色块。"
  };
  var THRESHOLD_TEXT = {
    auto: "自动",
    otsu: "全局",
    adaptive: "自适应",
    manual: "手动"
  };
  var THRESHOLD_DESCRIPTION = {
    auto: "根据背景光照自动选择全局或局部自适应阈值。",
    otsu: "全局阈值（Otsu），背景均匀的图片效果最稳。",
    adaptive: "局部自适应阈值，适合光照不均的扫描件。",
    manual: "固定阈值，使用下方滑块手动调节墨迹判定。"
  };
  var ALLOWED_EXTENSIONS = [
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif",
    ".ico", ".tga", ".jp2", ".j2k", ".ppm", ".pgm", ".pbm", ".pnm"
  ];
  var MAX_FILE_BYTES = 36 * 1024 * 1024;
  var DEBOUNCE_MS = 340;
  var numberFormatter = new Intl.NumberFormat("zh-CN");

  /* ---------- DOM ---------- */
  function byId(id) {
    return document.getElementById(id);
  }

  var els = {
    servicePill: byId("servicePill"),
    serviceText: byId("serviceText"),
    fileInput: byId("fileInput"),
    dropzone: byId("dropzone"),
    fileMeta: byId("fileMeta"),
    fileThumb: byId("fileThumb"),
    fileName: byId("fileName"),
    fileDims: byId("fileDims"),
    fileSize: byId("fileSize"),
    clearImage: byId("clearImage"),
    changeImage: byId("changeImage"),
    uploadNote: byId("uploadNote"),
    resetOptions: byId("resetOptions"),
    modeValue: byId("modeValue"),
    modeNote: byId("modeNote"),
    precisionInput: byId("precisionInput"),
    precisionValue: byId("precisionValue"),
    gapInput: byId("gapInput"),
    gapValue: byId("gapValue"),
    smoothInput: byId("smoothInput"),
    smoothValue: byId("smoothValue"),
    thresholdNote: byId("thresholdNote"),
    manualField: byId("manualField"),
    thresholdInput: byId("thresholdInput"),
    thresholdValue: byId("thresholdValue"),
    dpiInput: byId("dpiInput"),
    cornerInput: byId("cornerInput"),
    cornerValue: byId("cornerValue"),
    minDetailInput: byId("minDetailInput"),
    minDetailValue: byId("minDetailValue"),
    dxfVersion: byId("dxfVersion"),
    samplesGrid: byId("samplesGrid"),
    samplesEmpty: byId("samplesEmpty"),
    samplesCount: byId("samplesCount"),
    stage: byId("stage"),
    stageMedia: byId("stageMedia"),
    originalImg: byId("originalImg"),
    svgHost: byId("svgHost"),
    stageEmpty: byId("stageEmpty"),
    stageLoading: byId("stageLoading"),
    stageLoadingText: byId("stageLoadingText"),
    stageError: byId("stageError"),
    stageErrorText: byId("stageErrorText"),
    retryBtn: byId("retryBtn"),
    statusText: byId("statusText"),
    statusLabel: byId("statusLabel"),
    statusMeta: byId("statusMeta"),
    overlayField: byId("overlayField"),
    overlayInput: byId("overlayInput"),
    overlayValue: byId("overlayValue"),
    statsGrid: byId("statsGrid"),
    resultEmpty: byId("resultEmpty"),
    resultBody: byId("resultBody"),
    autoReason: byId("autoReason"),
    warnBlock: byId("warnBlock"),
    warnList: byId("warnList"),
    downloadDxf: byId("downloadDxf"),
    downloadSvg: byId("downloadSvg"),
    toasts: byId("toasts"),
    liveStatus: byId("liveStatus"),
    footerVersion: byId("footerVersion")
  };

  var modeButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-mode]")
  );
  var thresholdButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-threshold]")
  );
  var invertButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-invert]")
  );
  var dpiButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-dpi]")
  );
  var presetButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-preset]")
  );
  var tabButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-tab]")
  );

  var stageEmptyTitle = document.querySelector("#stageEmpty .stage-title");
  var stageEmptyDesc = document.querySelector("#stageEmpty .stage-desc");

  var RANGE_INPUTS = [
    "precisionInput",
    "gapInput",
    "smoothInput",
    "thresholdInput",
    "cornerInput",
    "minDetailInput",
    "overlayInput"
  ];

  /* ---------- 状态 ---------- */
  var state = {
    file: null,
    fileBase64: null,
    objectUrl: null,
    imageSize: null,
    canPreviewOriginal: false,
    options: Object.assign({}, DEFAULT_OPTIONS),
    requestSeq: 0,
    debounceTimer: null,
    pending: false,
    result: null,
    hasResult: false,
    tab: "original",
    overlay: 0.7,
    samples: [],
    sampleLoading: false,
    lastError: "",
    svgBlobUrl: null,
    scrolledForFile: false
  };

  var healthTimer = null;
  var resizeObserver = null;

  /* ======================================================================
     初始化
     ====================================================================== */
  function init() {
    bindUploadEvents();
    bindOptionEvents();
    bindPreviewEvents();
    bindSamplesEvents();
    bindKeyboardEvents();

    RANGE_INPUTS.forEach(function (id) {
      updateRangeFill(els[id]);
    });
    syncOptionsUI();
    els.overlayValue.textContent = "70%";
    els.stage.style.setProperty("--overlay-opacity", String(state.overlay));
    applyTab("original");
    clearDownloads();
    refreshStageVisibility();
    setStatus("idle", "等待图片");
    updateEmptyState();

    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(function () {
        updateMediaSize();
      });
      resizeObserver.observe(els.stage);
    }
    window.addEventListener("resize", updateMediaSize);

    checkHealth();
    loadSamples();
  }

  /* ======================================================================
     健康检查 / 服务状态
     ====================================================================== */
  function setServiceStatus(ok, text) {
    els.servicePill.classList.remove("pill--muted", "pill--ok", "pill--error");
    els.servicePill.classList.add(ok ? "pill--ok" : "pill--error");
    els.serviceText.textContent = text;
  }

  function checkHealth() {
    return fetch("/api/health", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        if (!data || data.ok !== true || data.service !== "bmp2dxf") {
          throw new Error("服务响应异常");
        }
        setServiceStatus(true, "服务已就绪 · v" + data.version);
        els.footerVersion.textContent = "bmp2dxf v" + data.version;
        if (healthTimer) {
          clearInterval(healthTimer);
          healthTimer = null;
        }
      })
      .catch(function () {
        setServiceStatus(false, "本地服务未连接");
        els.footerVersion.textContent = "版本不可用";
        if (!healthTimer) {
          healthTimer = setInterval(checkHealth, 8000);
        }
      });
  }

  /* ======================================================================
     文件上传
     ====================================================================== */
  function bindUploadEvents() {
    els.fileInput.addEventListener("change", function () {
      var files = els.fileInput.files;
      if (files && files.length) {
        loadFile(files[0]);
      }
      els.fileInput.value = "";
    });

    els.changeImage.addEventListener("click", function () {
      els.fileInput.click();
    });

    els.clearImage.addEventListener("click", clearFile);

    els.dropzone.addEventListener("click", function () {
      els.fileInput.click();
    });

    els.dropzone.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        els.fileInput.click();
      }
    });

    ["dragenter", "dragover"].forEach(function (name) {
      document.addEventListener(name, function (event) {
        if (!eventHasFiles(event)) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        els.dropzone.classList.add("is-dragover");
        if (event.dataTransfer) {
          event.dataTransfer.dropEffect = "copy";
        }
      });
    });

    document.addEventListener("dragleave", function (event) {
      if (!event.relatedTarget) {
        els.dropzone.classList.remove("is-dragover");
      }
    });

    document.addEventListener("drop", function (event) {
      if (!eventHasFiles(event)) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      els.dropzone.classList.remove("is-dragover");
      var files = event.dataTransfer && event.dataTransfer.files;
      if (files && files.length) {
        loadFile(files[0]);
      }
    });
  }

  function eventHasFiles(event) {
    var types = event.dataTransfer && event.dataTransfer.types;
    if (!types) {
      return false;
    }
    for (var i = 0; i < types.length; i += 1) {
      if (types[i] === "Files") {
        return true;
      }
    }
    return false;
  }

  function extensionOf(name) {
    var text = String(name || "");
    var index = text.lastIndexOf(".");
    return index >= 0 ? text.slice(index).toLowerCase() : "";
  }

  function validateFile(file) {
    if (!file) {
      return "没有读取到文件，请重新选择图片。";
    }
    if (file.size === 0) {
      return "这个文件是空的，请选择有效的图片。";
    }
    if (file.size > MAX_FILE_BYTES) {
      return (
        "图片文件过大（" +
        formatBytes(file.size) +
        "）。为保证浏览器与服务性能，请先压缩到 36 MB 以内。"
      );
    }
    var isImage = typeof file.type === "string" && file.type.indexOf("image/") === 0;
    if (!isImage && ALLOWED_EXTENSIONS.indexOf(extensionOf(file.name)) === -1) {
      return "不支持的文件类型。请选择 PNG / JPEG / WebP / BMP / TIFF / GIF 图片。";
    }
    return "";
  }

  function readFileAsDataURL(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || ""));
      };
      reader.onerror = function () {
        reject(reader.error || new Error("无法读取文件"));
      };
      reader.readAsDataURL(file);
    });
  }

  function imageSizeFromUrl(url) {
    return new Promise(function (resolve, reject) {
      var image = new Image();
      image.onload = function () {
        resolve({ width: image.naturalWidth, height: image.naturalHeight });
      };
      image.onerror = function () {
        reject(new Error("浏览器无法解码该图片"));
      };
      image.src = url;
    });
  }

  function normalizeClipboardFile(file) {
    if (!file) {
      return null;
    }
    var name = file.name || "clipboard.png";
    try {
      return new File([file], name, {
        type: file.type || "image/png"
      });
    } catch (error) {
      return file;
    }
  }

  function loadFile(file) {
    var problem = validateFile(file);
    if (problem) {
      showToast(problem, "error", 7000);
      return Promise.resolve(false);
    }
    if (file.size > 12 * 1024 * 1024) {
      showToast(
        "图片较大（" + formatBytes(file.size) + "），转换可能需要几秒钟。",
        "info",
        4200
      );
    }
    return readFileAsDataURL(file)
      .then(function (dataUrl) {
        var comma = dataUrl.indexOf(",");
        var base64 = comma >= 0 ? dataUrl.slice(comma + 1) : "";
        if (!base64) {
          throw new Error("图片数据为空");
        }
        var objectUrl = URL.createObjectURL(file);
        return imageSizeFromUrl(objectUrl)
          .then(function (size) {
            return {
              base64: base64,
              size: size,
              canPreview: true,
              objectUrl: objectUrl
            };
          })
          .catch(function () {
            return {
              base64: base64,
              size: null,
              canPreview: false,
              objectUrl: objectUrl
            };
          });
      })
      .then(function (prepared) {
        revokeObjectUrl();
        state.objectUrl = prepared.objectUrl;
        state.file = file;
        state.fileBase64 = prepared.base64;
        state.imageSize = prepared.size;
        state.canPreviewOriginal = prepared.canPreview;
        state.result = null;
        state.hasResult = false;
        state.lastError = "";
        state.scrolledForFile = false;
        state.requestSeq += 1; // 让旧请求的响应失效
        clearTimeout(state.debounceTimer);

        els.originalImg.hidden = !prepared.canPreview;
        if (prepared.canPreview) {
          els.originalImg.src = prepared.objectUrl;
        } else {
          els.originalImg.removeAttribute("src");
        }
        els.stageMedia.hidden = true;
        els.svgHost.replaceChildren();
        els.stageError.hidden = true;
        els.stageLoading.hidden = true;
        els.stage.classList.remove("is-loading");
        state.pending = false;
        clearDownloads();
        els.resultBody.hidden = true;
        els.resultEmpty.hidden = false;
        els.warnBlock.hidden = true;
        els.warnList.replaceChildren();
        els.statsGrid.replaceChildren();
        els.autoReason.textContent = "—";

        applyTab("original");
        renderFileMeta();
        setUploadedUI(true);
        updateEmptyState();
        refreshStageVisibility();
        setStatus("idle", "已选择图片，准备转换…");
        els.statusMeta.textContent = file.name + " · " + formatBytes(file.size);
        if (!prepared.canPreview) {
          showToast(
            "浏览器无法直接预览该格式，但转换可以正常进行；完成后请切换到「矢量」标签查看。",
            "info",
            6200
          );
        }
        scheduleConvert(120);
        return true;
      })
      .catch(function (error) {
        showToast(
          "读取图片失败：" +
            (error && error.message ? error.message : "未知错误"),
          "error",
          6500
        );
        return false;
      });
  }

  function renderFileMeta() {
    if (!state.file) {
      return;
    }
    var dims = state.imageSize;
    if (!dims && state.result) {
      dims = {
        width: state.result.source_width,
        height: state.result.source_height
      };
    }
    els.fileName.textContent = state.file.name;
    els.fileName.title = state.file.name;
    els.fileDims.textContent = dims
      ? dims.width + " × " + dims.height + " px"
      : "尺寸将在转换后显示";
    els.fileSize.textContent = formatBytes(state.file.size);
    els.fileMeta.hidden = false;
    els.dropzone.hidden = true;
    els.clearImage.disabled = false;
    if (state.objectUrl && state.canPreviewOriginal) {
      els.fileThumb.src = state.objectUrl;
      els.fileThumb.hidden = false;
    } else {
      els.fileThumb.removeAttribute("src");
      els.fileThumb.hidden = true;
    }
    els.uploadNote.textContent = "所有转换只在本机服务中完成，不会上传到网络。";
  }

  function setUploadedUI(hasFile) {
    els.fileMeta.hidden = !hasFile;
    els.dropzone.hidden = hasFile;
    els.clearImage.disabled = !hasFile;
  }

  function clearFile() {
    state.requestSeq += 1;
    clearTimeout(state.debounceTimer);
    revokeObjectUrl();
    if (state.svgBlobUrl) {
      URL.revokeObjectURL(state.svgBlobUrl);
      state.svgBlobUrl = null;
    }
    state.file = null;
    state.fileBase64 = null;
    state.imageSize = null;
    state.canPreviewOriginal = false;
    state.result = null;
    state.hasResult = false;
    state.pending = false;
    state.lastError = "";
    els.fileInput.value = "";
    els.originalImg.removeAttribute("src");
    els.svgHost.replaceChildren();
    els.stageMedia.hidden = true;
    els.stageEmpty.hidden = false;
    els.stageLoading.hidden = true;
    els.stageError.hidden = true;
    els.stage.classList.remove("is-loading");
    els.overlayField.hidden = true;
    setUploadedUI(false);
    clearDownloads();
    els.resultBody.hidden = true;
    els.resultEmpty.hidden = false;
    els.statsGrid.replaceChildren();
    els.warnBlock.hidden = true;
    els.warnList.replaceChildren();
    els.autoReason.textContent = "—";
    els.statusMeta.textContent = "";
    applyTab("original");
    updateEmptyState();
    refreshStageVisibility();
    setStatus("idle", "等待图片");
    els.liveStatus.textContent = "已清除图片";
  }

  function revokeObjectUrl() {
    if (state.objectUrl) {
      URL.revokeObjectURL(state.objectUrl);
      state.objectUrl = null;
    }
  }

  /* ======================================================================
     剪贴板粘贴
     ====================================================================== */
  function bindKeyboardEvents() {
    document.addEventListener("paste", function (event) {
      var clipboard = event.clipboardData;
      if (!clipboard) {
        return;
      }
      var items = clipboard.items || [];
      for (var i = 0; i < items.length; i += 1) {
        var item = items[i];
        if (
          item.kind === "file" &&
          item.type &&
          item.type.indexOf("image/") === 0
        ) {
          var file = normalizeClipboardFile(item.getAsFile());
          if (file) {
            event.preventDefault();
            loadFile(file);
          }
          return;
        }
      }
    });
  }

  /* ======================================================================
     参数控件
     ====================================================================== */
  function bindOptionEvents() {
    modeButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setOption("mode", button.getAttribute("data-mode"));
      });
    });

    thresholdButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        var method = button.getAttribute("data-threshold");
        if (method === "manual" && !isFiniteNumber(state.options.threshold)) {
          state.options.threshold = 128;
        }
        setOption("threshold_method", method);
      });
    });

    invertButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setOption("invert", button.getAttribute("data-invert"));
      });
    });

    dpiButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        setDpi(button.getAttribute("data-dpi"), true);
      });
    });

    els.precisionInput.addEventListener("input", function () {
      state.options.precision = clampNumber(
        els.precisionInput.valueAsNumber,
        0,
        100,
        70
      );
      afterOptionChange();
    });
    els.gapInput.addEventListener("input", function () {
      state.options.gap_close = clampNumber(
        els.gapInput.valueAsNumber,
        0,
        40,
        4
      );
      afterOptionChange();
    });
    els.smoothInput.addEventListener("input", function () {
      state.options.smoothing = clampNumber(
        els.smoothInput.valueAsNumber,
        0,
        100,
        55
      );
      afterOptionChange();
    });
    els.thresholdInput.addEventListener("input", function () {
      state.options.threshold = clampNumber(
        els.thresholdInput.valueAsNumber,
        0,
        255,
        128
      );
      afterOptionChange();
    });
    els.cornerInput.addEventListener("input", function () {
      state.options.corner_angle = clampNumber(
        els.cornerInput.valueAsNumber,
        20,
        170,
        100
      );
      afterOptionChange();
    });
    els.minDetailInput.addEventListener("input", function () {
      state.options.min_detail = clampNumber(
        els.minDetailInput.valueAsNumber,
        0,
        20,
        0
      );
      afterOptionChange();
    });

    els.dxfVersion.addEventListener("change", function () {
      state.options.dxf_version = els.dxfVersion.value;
      afterOptionChange();
    });

    els.dpiInput.addEventListener("change", function () {
      setDpi(els.dpiInput.value, true);
    });

    presetButtons.forEach(function (button) {
      button.addEventListener("click", function () {
        applyPreset(button.getAttribute("data-preset"));
      });
    });

    els.resetOptions.addEventListener("click", function () {
      state.options = Object.assign({}, DEFAULT_OPTIONS);
      clearPresetSelection();
      syncOptionsUI();
      scheduleConvert(150);
      showToast("已恢复默认参数", "info", 2200);
    });
  }

  function isFiniteNumber(value) {
    return typeof value === "number" && isFinite(value);
  }

  function clampNumber(value, min, max, fallback) {
    var number = Number(value);
    if (!isFinite(number)) {
      number = fallback;
    }
    return Math.min(max, Math.max(min, number));
  }

  function setOption(key, value) {
    state.options[key] = value;
    clearPresetSelection();
    syncOptionsUI();
    scheduleConvert();
  }

  function afterOptionChange() {
    clearPresetSelection();
    syncOptionsUI();
    scheduleConvert();
  }

  function setDpi(value, shouldConvert) {
    var dpi = clampNumber(Number(value), 10, 2400, 96);
    state.options.dpi = Math.round(dpi);
    clearPresetSelection();
    syncOptionsUI();
    if (shouldConvert) {
      scheduleConvert(160);
    }
  }

  function syncOptionsUI() {
    var options = state.options;
    setSegmented(modeButtons, "mode", options.mode);
    setSegmented(thresholdButtons, "threshold", options.threshold_method);
    setSegmented(invertButtons, "invert", options.invert);
    setSegmented(dpiButtons, "dpi", String(options.dpi));

    if (els.modeValue) {
      els.modeValue.textContent = MODE_TEXT[options.mode] || "";
    }
    els.modeNote.textContent = MODE_DESCRIPTION[options.mode] || "";
    els.thresholdNote.textContent =
      THRESHOLD_DESCRIPTION[options.threshold_method] || "";
    els.manualField.hidden = options.threshold_method !== "manual";

    setRangeValue(els.precisionInput, options.precision);
    els.precisionValue.textContent = String(options.precision);

    setRangeValue(els.gapInput, options.gap_close);
    els.gapValue.textContent = formatNumber(options.gap_close) + " px";

    setRangeValue(els.smoothInput, options.smoothing);
    els.smoothValue.textContent = String(options.smoothing);

    setRangeValue(els.thresholdInput, options.threshold);
    els.thresholdValue.textContent = String(Math.round(options.threshold));

    setRangeValue(els.cornerInput, options.corner_angle);
    els.cornerValue.textContent = formatNumber(options.corner_angle) + "°";

    setRangeValue(els.minDetailInput, options.min_detail);
    els.minDetailValue.textContent =
      options.min_detail > 0
        ? formatNumber(options.min_detail) + " px"
        : "自动";

    els.dpiInput.value = String(options.dpi);
    els.dxfVersion.value = options.dxf_version;
  }

  function setSegmented(buttons, dataKey, activeValue) {
    buttons.forEach(function (button) {
      var raw = button.getAttribute("data-" + dataKey);
      var active = raw === activeValue;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function setRangeValue(input, value) {
    var text = String(value);
    if (input.value !== text) {
      input.value = text;
    }
    updateRangeFill(input);
  }

  function updateRangeFill(input) {
    var min = parseFloat(input.min) || 0;
    var max = parseFloat(input.max) || 100;
    var value = parseFloat(input.value) || 0;
    var percent = max > min ? ((value - min) / (max - min)) * 100 : 0;
    percent = Math.min(100, Math.max(0, percent));
    input.style.setProperty("--fill", percent.toFixed(2) + "%");
  }

  function clearPresetSelection() {
    presetButtons.forEach(function (button) {
      button.classList.remove("is-active");
    });
  }

  function applyPreset(name) {
    var preset = PRESETS[name];
    if (!preset) {
      return;
    }
    Object.keys(preset.options).forEach(function (key) {
      state.options[key] = preset.options[key];
    });
    syncOptionsUI();
    presetButtons.forEach(function (button) {
      button.classList.toggle(
        "is-active",
        button.getAttribute("data-preset") === name
      );
    });
    scheduleConvert(140);
    showToast("已应用预设：" + preset.label, "info", 2000);
  }

  function buildPayloadOptions() {
    return {
      mode: state.options.mode,
      precision: state.options.precision,
      threshold_method: state.options.threshold_method,
      threshold:
        state.options.threshold_method === "manual"
          ? state.options.threshold
          : null,
      invert: state.options.invert,
      gap_close: state.options.gap_close,
      smoothing: state.options.smoothing,
      corner_angle: state.options.corner_angle,
      min_detail: state.options.min_detail,
      dpi: state.options.dpi,
      dxf_version: state.options.dxf_version
    };
  }

  /* ======================================================================
     转换请求
     ====================================================================== */
  function scheduleConvert(delay) {
    if (!state.file || !state.fileBase64) {
      return;
    }
    clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(function () {
      startConversion();
    }, typeof delay === "number" ? delay : DEBOUNCE_MS);
  }

  function ConvertError(message) {
    this.name = "ConvertError";
    this.message = message;
    this.stack = new Error(message).stack;
  }
  ConvertError.prototype = Object.create(Error.prototype);
  ConvertError.prototype.constructor = ConvertError;

  function startConversion() {
    clearTimeout(state.debounceTimer);
    if (!state.file || !state.fileBase64) {
      return;
    }
    var seq = ++state.requestSeq;
    enterLoading();
    var payload = {
      image_base64: state.fileBase64,
      filename: state.file.name,
      options: buildPayloadOptions()
    };

    fetch("/api/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(payload)
    })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            return { response: response, data: data };
          });
      })
      .then(function (result) {
        if (seq !== state.requestSeq) {
          return; // 过期响应：忽略，避免旧结果覆盖新结果
        }
        var response = result.response;
        var data = result.data;
        if (!response.ok || !data || data.ok !== true) {
          throw new ConvertError(
            data && data.error
              ? data.error
              : "转换失败（HTTP " + response.status + "）。"
          );
        }
        applyResult(data);
      })
      .catch(function (error) {
        if (seq !== state.requestSeq) {
          return;
        }
        showConversionError(
          error instanceof ConvertError
            ? error.message
            : "无法连接本地服务（" +
              (error && error.message ? error.message : "网络错误") +
              "）。请确认启动窗口仍在运行。"
        );
      })
      .finally(function () {
        if (seq === state.requestSeq) {
          leaveLoading();
        }
      });
  }

  function enterLoading() {
    state.pending = true;
    els.stage.classList.add("is-loading");
    els.stageLoading.hidden = false;
    els.stageLoadingText.textContent = state.hasResult
      ? "正在重新转换…"
      : "正在转换…";
    els.stageError.hidden = true;
    els.stageEmpty.hidden = true;
    setStatus("busy", "转换中…");
    els.liveStatus.textContent = "正在转换图片";
    refreshStageVisibility();
  }

  function leaveLoading() {
    state.pending = false;
    els.stage.classList.remove("is-loading");
    els.stageLoading.hidden = true;
    refreshStageVisibility();
  }

  function showConversionError(message) {
    state.lastError = message;
    els.stageErrorText.textContent = message;
    els.stageError.hidden = false;
    els.stageEmpty.hidden = true;
    els.stageLoading.hidden = true;
    els.stage.classList.remove("is-loading");
    setStatus("error", "转换失败");
    els.liveStatus.textContent = "转换失败：" + message;
    showToast(message, "error", 7000);
    refreshStageVisibility();
  }

  function applyResult(data) {
    var firstResult = !state.hasResult;
    state.result = data;
    state.hasResult = true;
    state.lastError = "";
    els.stageError.hidden = true;
    els.stageLoading.hidden = true;
    els.stage.classList.remove("is-loading");

    renderSvg(data.svg);
    if (!state.imageSize && data.source_width && data.source_height) {
      state.imageSize = {
        width: data.source_width,
        height: data.source_height
      };
    }
    if (firstResult && state.tab === "original") {
      applyTab("vector");
    }
    renderFileMeta();
    renderStats(data);
    renderWarnings(data.warnings || []);
    enableDownloads(data.downloads);
    els.resultBody.hidden = false;
    els.resultEmpty.hidden = true;
    updateEmptyState();
    refreshStageVisibility();
    updateMediaSize();

    var stats = data.stats || {};
    setStatus(
      "ok",
      "已更新 · " + Math.round(Number(stats.duration_ms) || 0) + " ms"
    );
    els.statusMeta.textContent =
      state.file.name +
      " · " +
      (data.source_width || 0) +
      "×" +
      (data.source_height || 0) +
      " px · " +
      formatBytes(state.file.size);
    els.liveStatus.textContent =
      "转换完成：共 " +
      (stats.path_count || 0) +
      " 条路径，" +
      (stats.point_count || 0) +
      " 个节点";

    if (firstResult && !state.scrolledForFile) {
      state.scrolledForFile = true;
      if (window.matchMedia("(max-width: 1180px)").matches) {
        try {
          els.stage.scrollIntoView({ behavior: "smooth", block: "start" });
        } catch (error) {
          /* 老浏览器忽略平滑滚动 */
        }
      }
    }
  }

  function renderSvg(svgText) {
    els.svgHost.replaceChildren();
    if (!svgText || typeof svgText !== "string") {
      return;
    }
    try {
      var parser = new DOMParser();
      var documentNode = parser.parseFromString(svgText, "image/svg+xml");
      var root = documentNode && documentNode.documentElement;
      if (
        !root ||
        String(root.nodeName).toLowerCase() !== "svg" ||
        documentNode.getElementsByTagName("parsererror").length > 0
      ) {
        throw new Error("SVG 解析失败");
      }
      var imported = document.importNode(root, true);
      imported.removeAttribute("width");
      imported.removeAttribute("height");
      imported.setAttribute("preserveAspectRatio", "xMidYMid meet");
      imported.setAttribute("aria-hidden", "true");
      imported.setAttribute("focusable", "false");
      els.svgHost.appendChild(imported);
      return;
    } catch (error) {
      // 兜底：用 blob 图片显示矢量结果。
      if (state.svgBlobUrl) {
        URL.revokeObjectURL(state.svgBlobUrl);
        state.svgBlobUrl = null;
      }
      var blob = new Blob([svgText], { type: "image/svg+xml;charset=utf-8" });
      var url = URL.createObjectURL(blob);
      state.svgBlobUrl = url;
      var image = document.createElement("img");
      image.alt = "矢量结果预览";
      image.src = url;
      image.style.cssText =
        "width:100%;height:100%;object-fit:contain;display:block;";
      els.svgHost.appendChild(image);
    }
  }

  function statItem(label, value, unit, accent) {
    var item = document.createElement("div");
    item.className = "stat" + (accent ? " stat--accent" : "");
    var labelNode = document.createElement("span");
    labelNode.className = "stat-label";
    labelNode.textContent = label;
    var valueNode = document.createElement("span");
    valueNode.className = "stat-value";
    valueNode.textContent = value;
    if (unit) {
      var unitNode = document.createElement("small");
      unitNode.textContent = unit;
      valueNode.appendChild(unitNode);
    }
    item.appendChild(labelNode);
    item.appendChild(valueNode);
    return item;
  }

  function renderStats(data) {
    var stats = data.stats || {};
    var modeText =
      MODE_TEXT[data.mode_used] || MODE_TEXT[stats.mode_used] || "—";
    var thresholdText =
      Math.round(Number(stats.threshold) || 0) +
      " · " +
      (THRESHOLD_TEXT[stats.threshold_method] ||
        stats.threshold_method ||
        "—");
    var items = [
      statItem("模式", modeText, "", true),
      statItem("路径数", formatNumber(stats.path_count)),
      statItem("节点数", formatNumber(stats.point_count)),
      statItem("闭合路径", formatNumber(stats.closed_path_count)),
      statItem("线长", fixedNumber(stats.total_length_mm, 1), "mm"),
      statItem("耗时", Math.round(Number(stats.duration_ms) || 0), "ms"),
      statItem(
        "工作分辨率",
        (stats.work_width || 0) + "×" + (stats.work_height || 0)
      ),
      statItem("阈值", thresholdText)
    ];
    els.statsGrid.replaceChildren.apply(els.statsGrid, items);
    els.autoReason.textContent = data.auto_reason || "—";
  }

  function renderWarnings(warnings) {
    els.warnList.replaceChildren();
    if (!warnings || !warnings.length) {
      els.warnBlock.hidden = true;
      return;
    }
    warnings.forEach(function (message) {
      var item = document.createElement("li");
      item.textContent = message;
      els.warnList.appendChild(item);
    });
    els.warnBlock.hidden = false;
  }

  function enableDownloads(downloads) {
    if (!downloads) {
      clearDownloads();
      return;
    }
    setDownload(els.downloadDxf, downloads.dxf);
    setDownload(els.downloadSvg, downloads.svg);
  }

  function setDownload(link, url) {
    if (!url) {
      clearDownload(link);
      return;
    }
    link.href = url;
    link.classList.remove("btn--disabled");
    link.setAttribute("aria-disabled", "false");
  }

  function clearDownload(link) {
    link.href = "#";
    link.classList.add("btn--disabled");
    link.setAttribute("aria-disabled", "true");
  }

  function clearDownloads() {
    clearDownload(els.downloadDxf);
    clearDownload(els.downloadSvg);
  }

  /* ======================================================================
     预览与视图
     ====================================================================== */
  function displayDimensions() {
    if (state.result && state.tab === "vector") {
      return {
        width:
          state.result.source_width ||
          (state.imageSize && state.imageSize.width),
        height:
          state.result.source_height ||
          (state.imageSize && state.imageSize.height)
      };
    }
    if (state.imageSize) {
      return state.imageSize;
    }
    if (state.result) {
      return {
        width: state.result.source_width,
        height: state.result.source_height
      };
    }
    return null;
  }

  function refreshStageVisibility() {
    var showMedia;
    if (state.tab === "original") {
      showMedia = Boolean(state.canPreviewOriginal && state.imageSize);
    } else if (state.tab === "vector") {
      showMedia = Boolean(state.result);
    } else {
      showMedia = Boolean(
        state.result || (state.canPreviewOriginal && state.imageSize)
      );
    }
    els.stageMedia.hidden = !showMedia;
    els.stageEmpty.hidden =
      showMedia || state.pending || !els.stageError.hidden;
    if (showMedia) {
      updateMediaSize();
    }
  }

  function updateMediaSize() {
    var dims = displayDimensions();
    if (!dims || !dims.width || !dims.height) {
      return;
    }
    var stage = els.stage;
    var computed = window.getComputedStyle(stage);
    var padX =
      (parseFloat(computed.paddingLeft) || 0) +
      (parseFloat(computed.paddingRight) || 0);
    var padY =
      (parseFloat(computed.paddingTop) || 0) +
      (parseFloat(computed.paddingBottom) || 0);
    var availableWidth = Math.max(80, stage.clientWidth - padX);
    var availableHeight = Math.max(80, stage.clientHeight - padY);
    var scale = Math.min(
      availableWidth / dims.width,
      availableHeight / dims.height,
      6
    );
    if (!isFinite(scale) || scale <= 0) {
      return;
    }
    var width = Math.max(32, Math.round(dims.width * scale));
    var height = Math.max(32, Math.round(dims.height * scale));
    els.stageMedia.style.width = width + "px";
    els.stageMedia.style.height = height + "px";
  }

  function updateEmptyState() {
    if (!stageEmptyTitle || !stageEmptyDesc) {
      return;
    }
    if (!state.file) {
      stageEmptyTitle.textContent = "还没有图片";
      stageEmptyDesc.textContent =
        "从左侧上传或拖入一张线稿，转换结果会实时显示在这里。";
    } else if (!state.canPreviewOriginal) {
      stageEmptyTitle.textContent = "该格式无法在浏览器中直接预览";
      stageEmptyDesc.textContent =
        "转换仍会正常进行，完成后切换到「矢量」标签即可查看结果。";
    } else if (!state.result) {
      stageEmptyTitle.textContent = "正在生成矢量预览";
      stageEmptyDesc.textContent = "转换完成后会自动显示在这里。";
    } else {
      stageEmptyTitle.textContent = "暂无预览";
      stageEmptyDesc.textContent =
        "切换到「矢量」或「叠加」标签查看转换结果。";
    }
  }

  function applyTab(tab) {
    var valid = ["original", "vector", "overlay"];
    if (valid.indexOf(tab) === -1) {
      tab = "original";
    }
    state.tab = tab;
    tabButtons.forEach(function (button) {
      var active = button.getAttribute("data-tab") === tab;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
    });
    els.stage.setAttribute("data-view", tab);
    var activeTab = tabButtons.filter(function (button) {
      return button.getAttribute("data-tab") === tab;
    })[0];
    if (activeTab && activeTab.id) {
      els.stage.setAttribute("aria-labelledby", activeTab.id);
    }
    els.overlayField.hidden = !(tab === "overlay" && state.result);
    if (tab === "overlay") {
      els.stage.style.setProperty("--overlay-opacity", String(state.overlay));
    }
    updateEmptyState();
    refreshStageVisibility();
  }

  function setStatus(kind, text) {
    els.statusText.classList.remove("is-busy", "is-ok", "is-error");
    if (kind === "busy" || kind === "ok" || kind === "error") {
      els.statusText.classList.add("is-" + kind);
    }
    els.statusLabel.textContent = text;
  }

  function bindPreviewEvents() {
    tabButtons.forEach(function (button, index) {
      button.addEventListener("click", function () {
        applyTab(button.getAttribute("data-tab"));
      });
      button.addEventListener("keydown", function (event) {
        var key = event.key;
        if (
          key !== "ArrowRight" &&
          key !== "ArrowLeft" &&
          key !== "Home" &&
          key !== "End"
        ) {
          return;
        }
        event.preventDefault();
        var next = index;
        if (key === "ArrowRight") {
          next = (index + 1) % tabButtons.length;
        } else if (key === "ArrowLeft") {
          next = (index - 1 + tabButtons.length) % tabButtons.length;
        } else if (key === "Home") {
          next = 0;
        } else {
          next = tabButtons.length - 1;
        }
        tabButtons[next].focus();
        applyTab(tabButtons[next].getAttribute("data-tab"));
      });
    });

    els.overlayInput.addEventListener("input", function () {
      state.overlay = clampNumber(Number(els.overlayInput.value), 0.3, 1, 0.7);
      els.overlayValue.textContent = Math.round(state.overlay * 100) + "%";
      els.stage.style.setProperty("--overlay-opacity", String(state.overlay));
      updateRangeFill(els.overlayInput);
    });

    els.retryBtn.addEventListener("click", function () {
      startConversion();
    });

    [els.downloadDxf, els.downloadSvg].forEach(function (link) {
      link.addEventListener("click", function (event) {
        if (link.classList.contains("btn--disabled")) {
          event.preventDefault();
        }
      });
    });
  }

  /* ======================================================================
     示例画廊
     ====================================================================== */
  function bindSamplesEvents() {
    els.samplesGrid.addEventListener("click", function (event) {
      var target = event.target;
      var button =
        target && target.closest ? target.closest(".sample") : null;
      if (!button) {
        return;
      }
      var name = button.getAttribute("data-sample");
      var sample = null;
      for (var i = 0; i < state.samples.length; i += 1) {
        if (state.samples[i].name === name) {
          sample = state.samples[i];
          break;
        }
      }
      if (sample) {
        loadSample(sample, button);
      }
    });
  }

  function loadSamples() {
    els.samplesEmpty.hidden = true;
    return fetch("/api/samples", { cache: "no-store" })
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            return { response: response, data: data };
          });
      })
      .then(function (result) {
        if (!result.response.ok || !result.data || result.data.ok !== true) {
          throw new Error("示例列表加载失败");
        }
        state.samples = Array.isArray(result.data.samples)
          ? result.data.samples
          : [];
        renderSamples("");
      })
      .catch(function () {
        state.samples = [];
        renderSamples("示例列表暂时不可用，请确认本地服务正在运行。");
      });
  }

  function renderSamples(errorText) {
    els.samplesGrid.replaceChildren();
    if (!state.samples.length) {
      els.samplesEmpty.hidden = false;
      els.samplesEmpty.textContent =
        errorText || "samples/ 目录中还没有示例图片。";
      els.samplesCount.textContent = "";
      return;
    }
    els.samplesEmpty.hidden = true;
    els.samplesCount.textContent = state.samples.length + " 个";
    state.samples.forEach(function (sample) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "sample";
      button.setAttribute("data-sample", sample.name);
      button.title =
        (sample.display_name || sample.name) +
        (sample.width && sample.height
          ? " · " + sample.width + "×" + sample.height
          : "");

      var thumb = document.createElement("span");
      thumb.className = "sample-thumb";
      var image = document.createElement("img");
      image.src = sample.url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      thumb.appendChild(image);

      var name = document.createElement("span");
      name.className = "sample-name";
      name.textContent = sample.display_name || sample.name;

      var meta = document.createElement("span");
      meta.className = "sample-dims";
      if (sample.width && sample.height) {
        meta.textContent = sample.width + "×" + sample.height;
      } else if (typeof sample.size_bytes === "number") {
        meta.textContent = formatBytes(sample.size_bytes);
      }

      button.appendChild(thumb);
      button.appendChild(name);
      button.appendChild(meta);
      els.samplesGrid.appendChild(button);
    });
  }

  function loadSample(sample, button) {
    if (state.sampleLoading) {
      return;
    }
    state.sampleLoading = true;
    if (button) {
      button.classList.add("is-loading");
    }
    fetch(sample.url, { cache: "force-cache" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.blob();
      })
      .then(function (blob) {
        var fileName = sample.name || "sample.png";
        var file;
        try {
          file = new File([blob], fileName, {
            type: blob.type || "image/png"
          });
        } catch (error) {
          file = blob;
          file.name = fileName;
        }
        return loadFile(file);
      })
      .catch(function (error) {
        showToast(
          "加载示例失败：" +
            (error && error.message ? error.message : "未知错误"),
          "error",
          5200
        );
      })
      .finally(function () {
        state.sampleLoading = false;
        if (button) {
          button.classList.remove("is-loading");
        }
      });
  }

  /* ======================================================================
     工具函数与 Toast
     ====================================================================== */
  function formatNumber(value) {
    var number = Number(value);
    if (!isFinite(number)) {
      return "—";
    }
    return numberFormatter.format(number);
  }

  function fixedNumber(value, digits) {
    var number = Number(value);
    if (!isFinite(number)) {
      return "—";
    }
    return number.toFixed(digits);
  }

  function formatBytes(bytes) {
    var number = Number(bytes);
    if (!isFinite(number) || number < 0) {
      return "—";
    }
    if (number < 1024) {
      return Math.round(number) + " B";
    }
    if (number < 1024 * 1024) {
      return (number / 1024).toFixed(1) + " KB";
    }
    return (number / (1024 * 1024)).toFixed(2) + " MB";
  }

  function showToast(message, type, timeout) {
    if (!message) {
      return;
    }
    var toast = document.createElement("div");
    toast.className = "toast toast--" + (type || "info");
    var dot = document.createElement("span");
    dot.className = "toast-dot";
    dot.setAttribute("aria-hidden", "true");
    var text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(dot);
    toast.appendChild(text);
    els.toasts.appendChild(toast);
    while (els.toasts.children.length > 3) {
      els.toasts.removeChild(els.toasts.firstChild);
    }
    window.requestAnimationFrame(function () {
      toast.classList.add("is-visible");
    });
    var duration = typeof timeout === "number" ? timeout : 4600;
    var remove = function () {
      toast.classList.remove("is-visible");
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 260);
    };
    setTimeout(remove, duration);
    toast.addEventListener("click", remove);
  }

  /* ======================================================================
     启动
     ====================================================================== */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
