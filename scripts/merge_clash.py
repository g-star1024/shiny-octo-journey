#!/usr/bin/env python3
import requests
import yaml
import sys
import socket
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
    "https://gcore.jsdelivr.net/gh/qmqv/jd02/cla02-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd01/cla01-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd03/cla03-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd04/cla04-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd05/cla05-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd06/cla06-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd07/cla07-1010.yaml",
    "https://gcore.jsdelivr.net/gh/qmqv/jd08/cla08-1010.yaml",
    "https://api.dler.io/sub?target=clash&url=https%3A%2F%2Fsub.proxygo.org%2Fv2ray.php%3Fkey%3D0b90e69dfee5c4022fc4ccda739402e5&insert=false&emoji=true&list=false&tfo=false&scv=true&fdn=false&expand=true&sort=false&new_name=true",
    "https://api.dler.io/sub?target=clash&url=https%3A%2F%2Fproxy.v2gh.com%2Fhttps%3A%2F%2Fraw.githubusercontent.com%2FPawdroid%2FFree-servers%2Fmain%2Fsub&insert=false&emoji=true&list=false&tfo=false&scv=true&fdn=false&expand=true&sort=false&new_name=true",
    "https://url.v1.mk/sub?target=clash&url=https%3A%2F%2Fdl.itworker.cc.cd%2Fitworker%2Fsub&insert=false&config=https%3A%2F%2Fraw.githubusercontent.com%2FbyJoey%2Ftest%2Frefs%2Fheads%2Fmain%2Ftist.ini&emoji=true&list=false&xudp=false&udp=false&tfo=false&expand=true&scv=false&fdn=false&new_name=true"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 测试参数
TCP_TIMEOUT = 3           # 连接超时秒数
MAX_WORKERS = 20          # 并发测试线程数

def download_yaml(url):
    """下载并解析 YAML，返回 parsed dict，失败返回 None"""
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
    """合并 proxies，根据 name 去重（保留第一个出现的）"""
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

def check_proxy(proxy):
    """
    测试一个代理节点的 TCP 连通性。
    返回 (proxy, is_alive)
    """
    name = proxy.get('name', 'unknown')
    server = proxy.get('server')
    port = proxy.get('port')
    if not server or not port:
        print(f"Skipping {name}: missing server or port", file=sys.stderr)
        return proxy, False

    try:
        # 尝试 TCP 连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TCP_TIMEOUT)
        # 解析域名并连接
        sock.connect((server, port))
        sock.close()
        # print(f"Alive: {name} ({server}:{port})")
        return proxy, True
    except Exception as e:
        print(f"Timeout/Dead: {name} ({server}:{port}) - {type(e).__name__}", file=sys.stderr)
        return proxy, False

def filter_alive_proxies(proxies):
    """
    并发测试所有节点，只返回可连接的节点列表
    """
    if not proxies:
        return []
    alive = []
    total = len(proxies)
    print(f"Testing {total} proxies with {MAX_WORKERS} workers (timeout={TCP_TIMEOUT}s)...")
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_proxy = {executor.submit(check_proxy, proxy): proxy for proxy in proxies}
        for i, future in enumerate(as_completed(future_to_proxy), 1):
            proxy, is_alive = future.result()
            if is_alive:
                alive.append(proxy)
            # 每测试 10 个打印一次进度
            if i % 10 == 0 or i == total:
                print(f"Progress: {i}/{total} tested, {len(alive)} alive so far")
    print(f"Filtered: {len(alive)} alive out of {total} total nodes")
    return alive

def find_target_group(config):
    """
    找到应该被转换为 url-test 的代理组。
    返回 (group_index, group_name)
    """
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

def main():
    all_proxies = []
    base_config = None

    # 1. 下载所有配置，收集所有 proxies
    for url in URLS:
        print(f"Processing {url}")
        config = download_yaml(url)
        if not config:
            continue
        proxies = config.get('proxies')
        if proxies and isinstance(proxies, list):
            all_proxies.extend(proxies)
        if base_config is None and config.get('proxy-groups') and config.get('rules'):
            base_config = config
            print(f"Using base config from {url}")

    if not all_proxies:
        print("No proxies found, exiting", file=sys.stderr)
        sys.exit(1)

    # 去重
    all_proxies = merge_proxies(all_proxies)
    print(f"Total unique proxies before filtering: {len(all_proxies)}")

    # 2. 过滤掉 timeout 的节点（TCP 连通性测试）
    alive_proxies = filter_alive_proxies(all_proxies)

    if not alive_proxies:
        print("No alive proxies remaining, exiting", file=sys.stderr)
        sys.exit(1)

    # 3. 构建最终配置（使用可用节点）
    if base_config:
        final_config = copy.deepcopy(base_config)
        final_config['proxies'] = alive_proxies

        target_idx, target_name = find_target_group(final_config)
        if target_idx is not None:
            target_group = final_config['proxy-groups'][target_idx]
            target_group['type'] = 'url-test'
            target_group['url'] = 'http://www.gstatic.com/generate_204'
            target_group['interval'] = 300
            target_group['tolerance'] = 50
            proxy_names = [p['name'] for p in alive_proxies]
            target_group['proxies'] = proxy_names
            print(f"Converted group '{target_name}' to url-test with {len(proxy_names)} proxies")
        else:
            print("No suitable proxy group found, creating a new url-test group", file=sys.stderr)
            proxy_names = [p['name'] for p in alive_proxies]
            auto_group = {
                "name": "AUTO",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names
            }
            final_config.setdefault('proxy-groups', []).append(auto_group)
            rules = final_config.get('rules', [])
            modified = False
            for i, rule in enumerate(rules):
                if rule.startswith('MATCH,'):
                    rules[i] = "MATCH,AUTO"
                    modified = True
                    break
            if not modified:
                rules.append("MATCH,AUTO")
    else:
        # 无基础配置，创建默认
        print("No base config found, creating default config with url-test", file=sys.stderr)
        proxy_names = [p['name'] for p in alive_proxies]
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
                    "proxies": proxy_names
                }
            ],
            "rules": ["MATCH,AUTO"]
        }

    # 4. 写入文件
    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("Merged config written to clash/merged.yaml")

if __name__ == "__main__":
    main()
