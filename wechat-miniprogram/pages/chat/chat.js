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
    const sessionId = wx.getStorageSync("chat_session_id") || "wx_" + Date.now();
    wx.setStorageSync("chat_session_id", sessionId);

    this.setData({
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
      msg.products = sd.products.map((p) => ({
        ...p,
        // 处理图片URL
        image_urls: (p.image_urls || []).map((url) => {
          if (url.startsWith("http")) return url;
          return this.data.apiBase + url;
        }),
      }));
    }

    // 提取引导选项
    if (sd.guide_mode && sd.options) {
      const options = sd.options;
      if (options.color_name && options.color_name.length > 0) {
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
