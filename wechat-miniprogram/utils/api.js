const app = getApp();

function request(method, url, data = {}) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBase + url,
      method: method,
      data: data,
      header: { "Content-Type": "application/json" },
      timeout: 30000,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res.data);
        }
      },
      fail: (err) => {
        reject({ error: "网络请求失败", detail: err });
      },
    });
  });
}

module.exports = {
  // 聊天接口
  chat: (query, sessionId) => request("POST", "/chat/query", {
    query: query,
    session_id: sessionId,
  }),

  // 获取产品列表
  getProducts: (params = {}) => request("GET", "/products", params),

  // 搜索产品
  searchProducts: (q) => request("GET", "/products", { q: q }),

  // 获取产品详情
  getProductDetail: (modelNo) => request("GET", `/products/${modelNo}`),

  // 健康检查
  health: () => request("GET", "/health"),
};
