# 股票板块轮动跟踪器 📈

每日跟踪非ST科创板涨停股、板块资金流向、成交量对比。

## 功能

- 🔥 涨停股按板块分类统计
- 💰 行业板块资金流向 TOP10
- 🎯 概念板块涨幅 TOP10
- 📊 板块成交量 vs 大盘对比
- 📝 每日要点总结

## 数据更新

- 自动更新：每天北京时间 8:00 和 20:00
- 手动更新：点击页面右下角刷新按钮

## 使用方法

直接访问 GitHub Pages 链接即可查看最新数据。

## 本地运行

```bash
# 安装依赖
pip install akshare pandas requests

# 抓取数据
python fetch_data.py

# 启动本地服务器
python -m http.server 8000
```

然后访问 http://localhost:8000
