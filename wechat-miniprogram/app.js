App({
  globalData: {
    apiBase: "http://192.168.6.178:8000/api",
  },

  onLaunch() {
    console.log("App Launch");
    // 检查本地缓存的会话ID
    const sessionId = wx.getStorageSync("chat_session_id");
    if (!sessionId) {
      wx.setStorageSync("chat_session_id", "wx_" + Date.now());
    }
  },
});
