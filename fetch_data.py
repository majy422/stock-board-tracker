#!/usr/bin/env python3
"""
股票板块轮动跟踪器 - 数据抓取脚本
每日抓取：非ST科创涨停股、板块资金流向、板块成交量
"""
import akshare as ak
import pandas as pd
import json
import os
import requests
from datetime import datetime, timedelta
from collections import Counter
from industry_map import fix_industry

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

# 创建绕过代理的 session
session = requests.Session()
session.trust_env = False

import time
import random

def get_eastmoney_data(fs, fields, pz=20, retries=10):
    """获取东方财富数据 - 尝试多个域名+重试"""
    domains = [
        'https://push2his.eastmoney.com',
        'https://push2.eastmoney.com',
    ]
    
    for attempt in range(retries):
        for domain in domains:
            try:
                url = f'{domain}/api/qt/clist/get'
                params = {
                    'fid': 'f62' if 'f62' in fields else 'f3',
                    'po': 1, 'pz': pz, 'pn': 1, 'np': 1,
                    'fs': fs,
                    'fields': fields,
                }
                resp = session.get(url, params=params, headers=HEADERS, timeout=15)
                if resp.status_code == 200 and resp.text.startswith('{'):
                    return resp.json()
            except:
                pass
        if attempt < retries - 1:
            time.sleep(2)
    return None

def get_zt_stocks():
    """获取今日涨停股票（非ST、科创板）"""
    try:
        df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return []
        
        # 过滤：排除ST，排除科创板(688开头)
        df = df[~df['名称'].str.contains('ST', case=False, na=False)]
        df = df[~df['代码'].str.startswith('688')]
        
        results = []
        for _, row in df.iterrows():
            results.append({
                'code': row.get('代码', ''),
                'name': row.get('名称', ''),
                'price': float(row.get('最新价', 0)),
                'change_pct': float(row.get('涨跌幅', 0)),
                'amount': float(row.get('成交额', 0)),
                'turnover': float(row.get('换手率', 0)),
                'industry': fix_industry(row.get('所属行业', '')),
                'reason': row.get('涨停统计', ''),
                'continuous': int(row.get('连板数', 1)),
                'first_time': row.get('首次封板时间', ''),
                'seal_amount': float(row.get('封板资金', 0)),
            })
        return results
    except Exception as e:
        print(f"获取涨停股出错: {e}")
        return []

def get_industry_fund_flow_sina():
    """从新浪获取行业板块数据"""
    try:
        url = 'https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php'
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://finance.sina.com.cn',
        }
        resp = session.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return []
        
        # 解析 var S_Finance_bankuai_sinaindustry = {...}
        text = resp.text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start < 0 or end <= start:
            return []
        
        import json
        raw = json.loads(text[start:end])
        results = []
        for key, val in raw.items():
            parts = val.split(',')
            if len(parts) >= 8:
                results.append({
                    'name': parts[1],
                    'code': parts[0],
                    'net_inflow': float(parts[6]),  # 成交额
                    'rise_count': int(parts[2]),
                    'fall_count': 0,
                    'change_pct': float(parts[4]) if parts[4] else 0,
                })
        # 按成交额排序取前20
        results.sort(key=lambda x: x['net_inflow'], reverse=True)
        return results[:20]
    except Exception as e:
        print(f"新浪行业板块接口也失败: {e}")
        return []

def get_industry_fund_flow_eastmoney():
    """获取行业板块资金流向 - 东方财富API"""
    try:
        data = get_eastmoney_data(
            fs='m:90+t:2',
            fields='f12,f14,f2,f3,f62,f204,f205',
            pz=20
        )
        
        if not data:
            raise Exception('无法获取数据')
        
        results = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                results.append({
                    'name': item.get('f14', ''),
                    'code': item.get('f12', ''),
                    'net_inflow': float(item.get('f62', 0)),
                    'rise_count': 0,
                    'fall_count': 0,
                    'change_pct': float(item.get('f3', 0)),
                })
        return results
    except Exception as e:
        print(f"获取行业资金流向出错: {e}")
        return []

def retry_with_delay(func, label, min_results=1, max_retries=3, base_delay=3):
    """带重试的数据抓取包装器"""
    for attempt in range(max_retries):
        results = func()
        if results and len(results) >= min_results:
            print(f"  {label}: 成功获取 {len(results)} 条数据")
            return results
        if attempt < max_retries - 1:
            delay = base_delay * (attempt + 1) + random.uniform(0, 2)
            print(f"  {label}: 数据为空(第{attempt+1}次)，{delay:.1f}秒后重试...")
            time.sleep(delay)
    print(f"  {label}: 重试{max_retries}次后仍为空")
    return results or []

def get板块历史资金流(secid, target_dates):
    """从东方财富历史K线接口获取板块资金流向（真实历史数据）"""
    url = 'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
    params = {
        'lmt': '0', 'klt': '101',
        'fields1': 'f1,f2,f3,f7',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65',
        'ut': 'b2884a393a59ad64002292a3e90d46a5',
        'secid': secid,
    }
    try:
        resp = session.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if not data.get('data') or not data['data'].get('klines'):
            return {}
        result = {}
        for kline in data['data']['klines']:
            parts = kline.split(',')
            date = parts[0]
            if date in target_dates:
                result[date] = {
                    'net_inflow': float(parts[1]),  # 主力净流入
                    'change_pct': float(parts[7]),   # 涨跌幅
                }
        return result
    except:
        return {}

def fetch_historical_fund_flow(target_dates):
    """抓取历史日期的行业和概念板块资金流向（真实数据）"""
    print(f"\n抓取历史资金流向: {target_dates}")
    
    for fs, label in [('m:90+t:2', '行业'), ('m:90+t:3', '概念')]:
        # 获取板块列表
        板块列表 = []
        data = get_eastmoney_data(fs, 'f12,f14', pz=300)
        if data and data.get('data') and data['data'].get('diff'):
            板块列表 = [{'code': i.get('f12',''), 'name': i.get('f14','')} for i in data['data']['diff']]
        print(f"  {label}板块: {len(板块列表)} 个")
        
        按日期 = {d: [] for d in target_dates}
        for i, b in enumerate(板块列表):
            secid = f"90.{b['code']}"
            hist = get板块历史资金流(secid, target_dates)
            for d in target_dates:
                if d in hist:
                    按日期[d].append({
                        'name': b['name'], 'code': b['code'],
                        'net_inflow': hist[d]['net_inflow'],
                        'change_pct': hist[d]['change_pct'],
                        'rise_count': 0, 'fall_count': 0,
                    })
            if (i+1) % 50 == 0:
                print(f"    进度: {i+1}/{len(板块列表)}")
            time.sleep(0.08)
        
        for d in target_dates:
            按日期[d].sort(key=lambda x: x['net_inflow'], reverse=True)
            按日期[d] = 按日期[d][:20]
        
        # 写入文件
        for dk, fd in [('20260707','2026-07-07'), ('20260708','2026-07-08')]:
            if fd in target_dates:
                fp = os.path.join(DATA_DIR, f'{dk}.json')
                if os.path.exists(fp):
                    with open(fp) as f:
                        d = json.load(f)
                    key = 'industry_flow' if label == '行业' else 'concept_flow'
                    d[key] = 按日期.get(fd, [])
                    with open(fp, 'w', encoding='utf-8') as f:
                        json.dump(d, f, ensure_ascii=False, indent=2)
                    print(f"    {dk} {label}: {len(d[key])} 条")

def get_industry_fund_flow():
    """获取行业板块资金流向 - 先试东方财富，失败则用新浪，都重试"""
    def try_eastmoney():
        return get_industry_fund_flow_eastmoney()
    def try_sina():
        return get_industry_fund_flow_sina()
    
    # 先试东方财富，重试3次
    results = retry_with_delay(try_eastmoney, '行业资金流向(东方财富)', min_results=5, max_retries=3)
    if results:
        return results
    # 备用：新浪，重试3次
    print("东方财富行业接口失败，尝试新浪接口...")
    return retry_with_delay(try_sina, '行业资金流向(新浪)', min_results=5, max_retries=3)

def get_concept_fund_flow_one():
    """获取概念板块资金流向 - 单次尝试"""
    data = get_eastmoney_data(
        fs='m:90+t:3',
        fields='f12,f14,f2,f3,f62,f204,f205',
        pz=20
    )
    
    if not data:
        raise Exception('无法获取数据')
    
    results = []
    if data.get('data') and data['data'].get('diff'):
        for item in data['data']['diff']:
            results.append({
                'name': item.get('f14', ''),
                'code': item.get('f12', ''),
                'net_inflow': float(item.get('f62', 0)),
                'change_pct': float(item.get('f3', 0)),
            })
    return results

def get_concept_fund_flow():
    """获取概念板块资金流向 - 带重试"""
    return retry_with_delay(get_concept_fund_flow_one, '概念板块资金流向', min_results=5, max_retries=3)

def get_sector_volume_one():
    """获取行业板块成交量 - 单次尝试"""
    data = get_eastmoney_data(
        fs='m:90+t:2',
        fields='f12,f14,f2,f3,f6,f8',
        pz=30
    )
    
    if not data:
        raise Exception('无法获取数据')
    
    results = []
    if data.get('data') and data['data'].get('diff'):
        for item in data['data']['diff']:
            results.append({
                'name': item.get('f14', ''),
                'volume': float(item.get('f6', 0)),
                'change_pct': float(item.get('f3', 0)),
                'turnover': float(item.get('f8', 0)),
            })
    return results

def get_sector_volume():
    """获取行业板块成交量 - 带重试"""
    return retry_with_delay(get_sector_volume_one, '板块成交量', min_results=5, max_retries=3)

def get_market_volume():
    """获取大盘成交量"""
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            return {
                'date': str(latest.get('date', '')),
                'volume': float(latest.get('volume', 0)),
                'close': float(latest.get('close', 0)),
                'change_pct': (float(latest.get('close', 0)) / float(prev.get('close', 1)) - 1) * 100,
            }
    except Exception as e:
        print(f"获取大盘数据出错: {e}")
    return {}

def generate_summary(data):
    """生成每日总结"""
    # 使用实际交易日期，而不是今天的日期
    trade_date = data.get('market', {}).get('date', datetime.now().strftime('%Y-%m-%d'))
    summary = {
        'date': trade_date,
        'total_zt': len(data.get('zt_stocks', [])),
        'key_points': [],
    }
    
    # 涨停股最多的板块
    if data.get('zt_stocks'):
        industry_count = Counter(s['industry'] for s in data['zt_stocks'] if s['industry'])
        if industry_count:
            top_industry = industry_count.most_common(5)
            summary['key_points'].append(f"🔥 涨停股集中板块：{'、'.join(f'{k}({v}只)' for k, v in top_industry)}")
    
    # 资金流入最多的板块
    if data.get('industry_flow'):
        top_inflow = [s for s in data['industry_flow'] if s['net_inflow'] > 0][:3]
        if top_inflow:
            names = [f"{s['name']}({s['net_inflow']/1e8:.1f}亿)" for s in top_inflow]
            summary['key_points'].append(f"💰 主力资金流入前三：{'、'.join(names)}")
        
        top_outflow = sorted(data['industry_flow'], key=lambda x: x['net_inflow'])[:3]
        if top_outflow and top_outflow[0]['net_inflow'] < 0:
            names = [f"{s['name']}({s['net_inflow']/1e8:.1f}亿)" for s in top_outflow]
            summary['key_points'].append(f"📤 主力资金流出前三：{'、'.join(names)}")
    
    # 概念板块涨幅
    if data.get('concept_flow'):
        top_concept = sorted(data['concept_flow'], key=lambda x: x['change_pct'], reverse=True)[:3]
        if top_concept:
            names = [f"{s['name']}(+{s['change_pct']:.2f}%)" for s in top_concept]
            summary['key_points'].append(f"🎯 概念板块涨幅前三：{'、'.join(names)}")
    
    # 大盘情况
    if data.get('market'):
        market = data['market']
        direction = "📈 上涨" if market.get('change_pct', 0) > 0 else "📉 下跌"
        vol_unit = "亿" if market.get('volume', 0) > 1e8 else "万"
        vol = market.get('volume', 0) / (1e8 if market.get('volume', 0) > 1e8 else 1e4)
        summary['key_points'].append(f"📊 大盘{direction}{abs(market.get('change_pct', 0)):.2f}%，成交额{vol:.0f}{vol_unit}")
    
    return summary

def fetch_all():
    """抓取所有数据"""
    print(f"开始抓取数据 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    data = {
        'update_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'zt_stocks': get_zt_stocks(),
        'industry_flow': get_industry_fund_flow(),
        'concept_flow': get_concept_fund_flow(),
        'sector_volume': get_sector_volume(),
        'market': get_market_volume(),
    }
    
    # 生成总结
    data['summary'] = generate_summary(data)
    
    # 保存数据
    output_file = os.path.join(DATA_DIR, 'latest.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 同时保存一份历史记录
    history_file = os.path.join(DATA_DIR, f"{datetime.now().strftime('%Y%m%d')}.json")
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 更新日期列表
    update_dates_list()
    
    print(f"数据抓取完成，保存到 {output_file}")
    print(f"涨停股数量: {len(data['zt_stocks'])}")
    print(f"行业板块资金流向: {len(data['industry_flow'])} 个")
    print(f"概念板块: {len(data['concept_flow'])} 个")
    print(f"总结: {data['summary'].get('key_points', [])}")
    
    return data

def update_dates_list():
    """更新可用日期列表"""
    dates = []
    for f in os.listdir(DATA_DIR):
        if f.endswith('.json') and f != 'latest.json' and f != 'dates.json':
            date_str = f.replace('.json', '')
            # 转换格式: 20260707 -> 2026-07-07
            if len(date_str) == 8:
                formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                dates.append(formatted)
    
    # 按日期倒序排列
    dates.sort(reverse=True)
    
    # 保存日期列表
    dates_file = os.path.join(DATA_DIR, 'dates.json')
    with open(dates_file, 'w', encoding='utf-8') as f:
        json.dump(dates, f)
    
    print(f"日期列表已更新，共 {len(dates)} 个日期")

if __name__ == "__main__":
    fetch_all()
