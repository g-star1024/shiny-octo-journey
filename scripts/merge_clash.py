#!/usr/bin/env python3
import requests
import yaml
import sys
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy

# 所有订阅源 URL
URLS = [
    "https://raw.githubusercontent.com/qmqv/jd03/refs/heads/main/cla03-1010.yaml",
    "https://raw.githubusercontent.com/chengaopan/AutoMergePublicNodes/master/list.meta.yml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/yudou66.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/clashmeta.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/blues.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/ndnode.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/nodev2ray.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/nodefree.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/v2rayshare.yaml",
    "https://gh-proxy.com/raw.githubusercontent.com/Barabama/FreeNodes/main/nodes/wenode.yaml",
    "https://api.dler.io/sub?target=clash&url=https%3A%2F%2Fsub.proxygo.org%2Fv2ray.php%3Fkey%3D0b90e69dfee5c4022fc4ccda739402e5&insert=false&emoji=true&list=false&tfo=false&scv=true&fdn=false&expand=true&sort=false&new_name=true",
    "https://api.dler.io/sub?target=clash&url=https%3A%2F%2Fproxy.v2gh.com%2Fhttps%3A%2F%2Fraw.githubusercontent.com%2FPawdroid%2FFree-servers%2Fmain%2Fsub&insert=false&emoji=true&list=false&tfo=false&scv=true&fdn=false&expand=true&sort=false&new_name=true",
    "https://url.v1.mk/sub?target=clash&url=https%3A%2F%2Fdl.itworker.cc.cd%2Fitworker%2Fsub&insert=false&config=https%3A%2F%2Fraw.githubusercontent.com%2FbyJoey%2Ftest%2Frefs%2Fheads%2Fmain%2Ftist.ini&emoji=true&list=false&xudp=false&udp=false&tfo=false&expand=true&scv=false&fdn=false&new_name=true"
]

HEADERS = {"User-Agent": "Mozilla/5.0"}
TCP_TIMEOUT = 3          # 测速超时（秒）
MAX_WORKERS = 20         # 并发线程数
SORT_BY_LATENCY = True   # 是否按延迟排序（从小到大）

def download_yaml(url):
    """下载并解析 YAML"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = yaml.safe_load(resp.text)
        if isinstance(data, dict):
            return data
        else:
            print(f"Warning: {url} 返回不是字典格式", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Error downloading {url}: {e}", file=sys.stderr)
        return None

def merge_proxies(all_proxies):
    """合并 proxies，根据 name 去重"""
    seen = set()
    merged = []
    for proxy in all_proxies:
        if not isinstance(proxy, dict) or 'name' not in proxy:
            continue
        name = proxy['name']
        if name not in seen:
            seen.add(name)
            merged.append(proxy)
    return merged

def check_proxy_speed(proxy):
    """
    测试单个节点的 TCP 连接延迟（测速）
    返回 (proxy, latency_ms) 或 (proxy, None) 表示超时/失败
    """
    name = proxy.get('name', 'unknown')
    server = proxy.get('server')
    port = proxy.get('port')
    if not server or not port:
        return proxy, None
    
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TCP_TIMEOUT)
        sock.connect((server, port))
        end = time.time()
        sock.close()
        latency_ms = (end - start) * 1000
        return proxy, latency_ms
    except Exception:
        return proxy, None

def filter_alive_proxies(proxies):
    """
    并发测速，过滤掉超时/失败的节点，
    返回存活节点列表（可选项：按延迟排序）
    """
    if not proxies:
        return []
    
    alive = []          # 存储 (proxy, latency_ms)
    total = len(proxies)
    print(f"测速中：共 {total} 个节点，并发数 {MAX_WORKERS}，超时阈值 {TCP_TIMEOUT} 秒")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_proxy = {executor.submit(check_proxy_speed, proxy): proxy for proxy in proxies}
        for i, future in enumerate(as_completed(future_to_proxy), 1):
            proxy, latency_ms = future.result()
            name = proxy.get('name', 'unknown')
            if latency_ms is not None:
                alive.append((proxy, latency_ms))
                print(f"[{i}/{total}] ✓ {name} - 延迟 {latency_ms:.1f} ms")
            else:
                print(f"[{i}/{total}] ✗ {name} - 超时/失败")
            
            # 每测 10 个或最后一个时打印统计
            if i % 10 == 0 or i == total:
                print(f"进度: {i}/{total}，当前存活 {len(alive)} 个")
    
    # 按延迟排序（可选）
    if SORT_BY_LATENCY:
        alive.sort(key=lambda x: x[1])
    
    # 提取代理对象列表
    alive_proxies = [proxy for proxy, _ in alive]
    
    # 计算平均延迟（仅存活节点）
    if alive:
        avg_latency = sum(lat for _, lat in alive) / len(alive)
        print(f"测速完成：存活 {len(alive_proxies)}/{total} 个节点，平均延迟 {avg_latency:.1f} ms")
    else:
        print("测速完成：无存活节点")
    
    return alive_proxies

def find_target_group(config):
    """找到应该被转换为 url-test 的代理组索引和名称"""
    proxy_groups = config.get('proxy-groups', [])
    if not proxy_groups:
        return None, None
    common_names = ['PROXY', 'ALL', 'GLOBAL', '选择', '节点选择', 'Proxy', 'global', 'proxy']
    for idx, group in enumerate(proxy_groups):
        if group.get('type') == 'select' and group.get('name') in common_names:
            return idx, group.get('name')
    for idx, group in enumerate(proxy_groups):
        if group.get('type') == 'select':
            return idx, group.get('name')
    return 0, proxy_groups[0].get('name')

def clean_proxy_groups(proxy_groups, alive_names):
    """清理代理组中失效的节点引用"""
    builtin_strategies = {'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'GLOBAL'}
    cleaned_groups = []
    for group in proxy_groups:
        if 'proxies' not in group:
            cleaned_groups.append(group)
            continue
        original = group['proxies']
        filtered = []
        for item in original:
            if item in builtin_strategies or item.startswith('.') or item.startswith('+'):
                filtered.append(item)
            elif item in alive_names:
                filtered.append(item)
            else:
                print(f"移除失效节点 '{item}' 从组 '{group.get('name')}'", file=sys.stderr)
        group['proxies'] = filtered
        cleaned_groups.append(group)
    return cleaned_groups

def main():
    all_proxies = []
    base_config = None

    # 下载所有订阅源
    for url in URLS:
        print(f"正在处理: {url}")
        config = download_yaml(url)
        if not config:
            continue
        proxies = config.get('proxies')
        if proxies and isinstance(proxies, list):
            all_proxies.extend(proxies)
        if base_config is None and config.get('proxy-groups') and config.get('rules'):
            base_config = config
            print(f"使用基础配置来自: {url}")

    if not all_proxies:
        print("未找到任何节点，退出", file=sys.stderr)
        sys.exit(1)

    # 去重
    all_proxies = merge_proxies(all_proxies)
    print(f"去重后节点数: {len(all_proxies)}")

    # 测速过滤（核心更新）
    alive_proxies = filter_alive_proxies(all_proxies)
    if not alive_proxies:
        print("没有存活节点，退出", file=sys.stderr)
        sys.exit(1)

    alive_names = {p['name'] for p in alive_proxies}

    # 构建最终配置
    if base_config:
        final_config = copy.deepcopy(base_config)
        final_config['proxies'] = alive_proxies
        final_config['proxy-groups'] = clean_proxy_groups(final_config.get('proxy-groups', []), alive_names)

        target_idx, target_name = find_target_group(final_config)
        if target_idx is not None:
            target_group = final_config['proxy-groups'][target_idx]
            target_group['type'] = 'url-test'
            target_group['url'] = 'http://www.gstatic.com/generate_204'
            target_group['interval'] = 300
            target_group['tolerance'] = 50
            target_group['proxies'] = list(alive_names)
            print(f"已将组 '{target_name}' 转换为 url-test，包含 {len(alive_names)} 个节点")
        else:
            auto_group = {
                "name": "AUTO",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": list(alive_names)
            }
            final_config.setdefault('proxy-groups', []).append(auto_group)
            rules = final_config.get('rules', [])
            for i, rule in enumerate(rules):
                if rule.startswith('MATCH,'):
                    rules[i] = "MATCH,AUTO"
                    break
    else:
        final_config = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": True,
            "mode": "rule",
            "log-level": "info",
            "external-controller": "0.0.0.0:9090",
            "proxies": alive_proxies,
            "proxy-groups": [
                {
                    "name": "AUTO",
                    "type": "url-test",
                    "url": "http://www.gstatic.com/generate_204",
                    "interval": 300,
                    "tolerance": 50,
                    "proxies": list(alive_names)
                }
            ],
            "rules": ["MATCH,AUTO"]
        }

    # 输出最终配置
    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("已生成合并配置: clash/merged.yaml")

if __name__ == "__main__":
    main()
