const api = require("../../utils/api");

Page({
  data: {
    messages: [],
    inputValue: "",
    sessionId: "",
    loading: false,
    scrollToId: "",
    apiBase: "",
  },

  onLoad() {
    const app = getApp();
    // 每次进入都生成新 session，清空历史从头开始
    const sessionId = "wx_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);

    this.setData({
      messages: [],
      sessionId: sessionId,
      apiBase: app.globalData.apiBase.replace("/api", ""),
    });

    // 发送欢迎语
    this.sendToBot("你好");
  },

  // 输入框变化
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  // 点击发送按钮
  onSend() {
    const text = this.data.inputValue.trim();
    if (!text || this.data.loading) return;

    // 添加用户消息
    this.addMessage("user", text);
    this.setData({ inputValue: "" });

    // 发送到后端
    this.sendToBot(text);
  },

  // 点击引导选项按钮
  onOptionTap(e) {
    const value = e.currentTarget.dataset.value;
    this.addMessage("user", value);
    this.sendToBot(value);
  },

  // 发送到后端
  async sendToBot(query) {
    this.setData({ loading: true });
    this.scrollToBottom();

    try {
      const res = await api.chat(query, this.data.sessionId);
      this.handleBotResponse(res);
    } catch (err) {
      console.error("API Error:", err);
      let errorMsg = "网络出了点问题，请检查：\n";
      errorMsg += "1. 后端服务是否已启动\n";
      errorMsg += "2. 手机和电脑是否在同一个WiFi\n";
      errorMsg += "3. 开发者工具是否勾选「不校验合法域名」";
      this.addMessage("bot", errorMsg);
    }

    this.setData({ loading: false });
    this.scrollToBottom();
  },

  // 处理机器人回复
  handleBotResponse(res) {
    const sd = res.structured_data || {};
    const msg = {
      id: Date.now(),
      role: "bot",
      text: res.answer || "",
      formattedText: this.formatText(res.answer || ""),
      products: [],
      options: [],
      optionsLabel: "",
    };

    // 提取产品数据
    if (sd.products && sd.products.length > 0) {
      msg.products = sd.products.map((p) => {
        const apiBase = this.data.apiBase;
        const rawUrls = p.image_urls || [];
        const imageUrls = rawUrls.map((url) => {
          if (url.indexOf("http") === 0) return url;
          return apiBase + url;
        });
        const area = p.area;
        const effArea = p.effective_area;
        return {
          ...p,
          _image_urls: imageUrls,
          applicable_models: (p.applicable_models || []).map((m) => {
            const rawUrls = m.image_urls || [];
            const imageUrls = rawUrls.map((url) => {
              if (url.indexOf("http") === 0) return url;
              return apiBase + url;
            });
            return {
              model_no: m.model_no,
              name: m.name || m.model_no,
              description: m.description || "",
              _image_urls: imageUrls,
              _has_image: imageUrls.length > 0,
              _local_image_url: "",
            };
          }),
          _color_display:
            p.related_options &&
            p.related_options.color_name &&
            p.related_options.color_name.length > 1
              ? p.related_options.color_name.join("、")
              : p.color_name || "-",
          rules_applied: p.rules_applied || [],
          warnings: p.warnings || [],
          _has_area: area != null,
          _has_effective_area: effArea != null && effArea !== area,
          _has_total_price: p.total_price != null,
        };
      });
    }

    // 提取引导选项
    if (sd.guide_mode && sd.options) {
      const options = sd.options;
      if (options.component_type && options.component_type.length > 0) {
        msg.options = options.component_type;
        msg.optionsLabel = "可选类型：";
      } else if (options.color_name && options.color_name.length > 0) {
        msg.options = options.color_name;
        msg.optionsLabel = "可选颜色：";
      } else if (options.substrate && options.substrate.length > 0) {
        msg.options = options.substrate;
        msg.optionsLabel = "可选基材：";
      } else if (options.thickness && options.thickness.length > 0) {
        msg.options = options.thickness.map((t) => t + "mm");
        msg.optionsLabel = "可选厚度：";
      }
    }

    this.addMessageObj(msg);
    // 预下载图片到本地（真机 <image> 组件加载 HTTP 图片受限，本地路径更可靠）
    const msgIndex = this.data.messages.length - 1;
    this.preloadImages(msgIndex);
  },

  // 格式化文本（把 markdown 粗体转成 rich-text 支持的格式）
  formatText(text) {
    if (!text) return "";
    // 先把换行转成 <br/>
    let html = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\n/g, '<br/>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>');
    return html;
  },

  // 添加用户消息（简单文本）
  addMessage(role, text) {
    const msg = {
      id: Date.now(),
      role: role,
      text: text,
      formattedText: this.formatText(text),
      products: [],
      options: [],
      optionsLabel: "",
    };
    this.addMessageObj(msg);
  },

  // 添加消息对象
  addMessageObj(msg) {
    const messages = [...this.data.messages, msg];
    this.setData({ messages: messages });
    this.scrollToBottom();
  },

  // 滚动到底部
  scrollToBottom() {
    const len = this.data.messages.length;
    if (len > 0) {
      this.setData({
        scrollToId: "msg-" + this.data.messages[len - 1].id,
      });
    }
  },

  // 预下载门型图片到本地
  preloadImages(msgIndex) {
    const msg = this.data.messages[msgIndex];
    if (!msg || !msg.products) return;
    msg.products.forEach((p, pIdx) => {
      (p.applicable_models || []).forEach((m, mIdx) => {
        if (m._image_urls && m._image_urls.length > 0 && !m._local_image_url) {
          wx.downloadFile({
            url: m._image_urls[0],
            success: (res) => {
              if (res.statusCode === 200) {
                const key = `messages[${msgIndex}].products[${pIdx}].applicable_models[${mIdx}]._local_image_url`;
                this.setData({ [key]: res.tempFilePath });
                console.log("图片下载成功", m._image_urls[0], res.tempFilePath);
              }
            },
            fail: (err) => {
              console.error("图片下载失败", m._image_urls[0], err);
            }
          });
        }
      });
    });
  },

  // 图片加载成功
  onImageLoad(e) {
    console.log("图片加载成功", e.currentTarget.dataset.index);
  },

  // 图片加载失败
  onImageError(e) {
    const idx = e.currentTarget.dataset.index;
    console.error("图片加载失败", idx, e);
    wx.showToast({ title: "图片加载失败", icon: "none" });
  },

  // 预览图片
  previewImage(e) {
    const urls = e.currentTarget.dataset.urls;
    const current = e.currentTarget.dataset.current;
    wx.previewImage({
      urls: urls,
      current: current,
    });
  },
});
