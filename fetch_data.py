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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

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
                'industry': row.get('所属行业', ''),
                'reason': row.get('涨停原因', ''),
            })
        return results
    except Exception as e:
        print(f"获取涨停股出错: {e}")
        return []

def get_industry_fund_flow():
    """获取行业板块资金流向 - 东方财富API"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'fid': 'f62',
            'po': 1,
            'pz': 20,
            'pn': 1,
            'np': 1,
            'fs': 'b:BK0475+f:!50',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124',
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
        results = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                results.append({
                    'name': item.get('f14', ''),
                    'code': item.get('f12', ''),
                    'net_inflow': float(item.get('f62', 0)),  # 主力净流入
                    'rise_count': int(item.get('f204', 0)),
                    'fall_count': int(item.get('f205', 0)),
                    'change_pct': float(item.get('f3', 0)),
                })
        return results
    except Exception as e:
        print(f"获取行业资金流向出错: {e}")
        return []

def get_concept_fund_flow():
    """获取概念板块资金流向 - 东方财富API"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'fid': 'f62',
            'po': 1,
            'pz': 20,
            'pn': 1,
            'np': 1,
            'fs': 'b:BK08+f:!50',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f204,f205,f124',
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
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
    except Exception as e:
        print(f"获取概念资金流向出错: {e}")
        return []

def get_sector_volume():
    """获取行业板块成交量"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'fid': 'f6',
            'po': 1,
            'pz': 30,
            'pn': 1,
            'np': 1,
            'fs': 'b:BK0475+f:!50',
            'fields': 'f12,f14,f2,f3,f6,f10,f8,f124',
        }
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        
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
    except Exception as e:
        print(f"获取板块成交量出错: {e}")
        return []

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
    summary = {
        'date': datetime.now().strftime("%Y-%m-%d"),
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
    
    print(f"数据抓取完成，保存到 {output_file}")
    print(f"涨停股数量: {len(data['zt_stocks'])}")
    print(f"行业板块资金流向: {len(data['industry_flow'])} 个")
    print(f"概念板块: {len(data['concept_flow'])} 个")
    print(f"总结: {data['summary'].get('key_points', [])}")
    
    return data

if __name__ == "__main__":
    fetch_all()
