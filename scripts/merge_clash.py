#!/usr/bin/env python3
import requests
import yaml
import sys
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy

# 配置项 ===================
TCP_TIMEOUT = 3          # TCP 连接超时（秒）
HTTP_TIMEOUT = 5         # HTTP 代理测速超时（秒）
MAX_WORKERS = 20         # 并发线程数
SORT_BY_LATENCY = True   # 是否按延迟排序
ENABLE_HTTP_TEST = True  # 是否启用真正的 HTTP 代理测速（需要 requests[socks] 支持）
TEST_URL = "http://www.gstatic.com/generate_204"  # 测速目标 URL

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

# ---------- 基础功能 ----------
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

# ---------- 核心测速部分 ----------
def tcp_test(server, port):
    """仅做 TCP 端口连通性测试，返回延迟毫秒或 None"""
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TCP_TIMEOUT)
        sock.connect((server, port))
        end = time.time()
        sock.close()
        return (end - start) * 1000
    except Exception:
        return None

def http_test(proxy):
    """
    通过代理发送真实的 HTTP 请求来测速
    proxy: Clash 节点配置字典
    返回 (success, latency_ms) 或 (False, None)
    仅支持 socks5, http, ss (通过 requests 的代理支持)
    """
    proxy_type = proxy.get('type', '').lower()
    server = proxy.get('server')
    port = proxy.get('port')
    if not server or not port:
        return False, None

    # 构建 requests 代理字典
    proxies = None
    if proxy_type in ('socks5', 'socks5h'):
        proxies = {
            'http': f'socks5://{server}:{port}',
            'https': f'socks5://{server}:{port}'
        }
    elif proxy_type in ('http', 'https'):
        proxies = {
            'http': f'http://{server}:{port}',
            'https': f'http://{server}:{port}'
        }
    elif proxy_type == 'ss':
        # Shadowsocks 需要额外参数，requests 无法直接使用，退化为 TCP 测速
        return False, None
    else:
        # 不支持的类型（trojan, vless, vmess 等）返回 False 表示无法测试，需要依赖 TCP 结果
        return False, None

    try:
        start = time.time()
        resp = requests.get(TEST_URL, proxies=proxies, timeout=HTTP_TIMEOUT, headers=HEADERS)
        end = time.time()
        if resp.status_code in (200, 204):
            latency_ms = (end - start) * 1000
            return True, latency_ms
        else:
            return False, None
    except Exception:
        return False, None

def check_proxy(proxy):
    """
    综合测速：
    1. 首先做 TCP 端口测试，若失败则直接标记为死亡
    2. 若 TCP 成功且 ENABLE_HTTP_TEST 为 True：
       - 如果节点类型支持 HTTP 代理测试，则做 HTTP 请求测试；成功才标记存活，否则死亡
       - 如果不支持 HTTP 测试，则仅凭 TCP 成功标记存活（并给出警告）
    """
    name = proxy.get('name', 'unknown')
    server = proxy.get('server')
    port = proxy.get('port')
    if not server or not port:
        return proxy, None

    # 步骤1：TCP 测试
    tcp_latency = tcp_test(server, port)
    if tcp_latency is None:
        return proxy, None

    # 步骤2：如果需要 HTTP 代理测试
    if ENABLE_HTTP_TEST:
        http_ok, http_latency = http_test(proxy)
        if http_ok:
            # 使用 HTTP 测速的延迟（更真实）
            return proxy, http_latency
        else:
            # HTTP 测试失败，但 TCP 成功：对于不支持的类型，根据配置决定是否保留
            proxy_type = proxy.get('type', 'unknown')
            # 如果是不支持 HTTP 测试的类型（trojan/vless/vmess），且 TCP 成功，可视为存活（降级）
            if proxy_type.lower() in ('trojan', 'vless', 'vmess', 'ss', ''):
                # 未识别类型或已知不支持的类型，依靠 TCP 结果，但给出提示
                print(f"   [提示] 节点 {name} 类型 {proxy_type} 不支持 HTTP 测速，仅通过 TCP 检测", file=sys.stderr)
                return proxy, tcp_latency
            else:
                # 支持 HTTP 但测试失败，说明节点实际不可用
                return proxy, None
    else:
        # 不启用 HTTP 测试，直接使用 TCP 结果
        return proxy, tcp_latency

def filter_alive_proxies(proxies):
    """
    并发测速，过滤掉超时/失败的节点
    返回存活节点列表（按延迟排序）
    """
    if not proxies:
        return []
    
    alive = []          # 存储 (proxy, latency_ms)
    total = len(proxies)
    print(f"开始测速：共 {total} 个节点，并发 {MAX_WORKERS}，TCP超时 {TCP_TIMEOUT}s，HTTP超时 {HTTP_TIMEOUT}s")
    if not ENABLE_HTTP_TEST:
        print("注意：HTTP 代理测速已禁用，仅使用 TCP 端口连通性检测，结果可能包含假存活节点")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_proxy = {executor.submit(check_proxy, proxy): proxy for proxy in proxies}
        for i, future in enumerate(as_completed(future_to_proxy), 1):
            proxy, latency_ms = future.result()
            name = proxy.get('name', 'unknown')
            if latency_ms is not None:
                alive.append((proxy, latency_ms))
                print(f"[{i}/{total}] ✓ {name} - 延迟 {latency_ms:.1f} ms")
            else:
                print(f"[{i}/{total}] ✗ {name} - 超时/失败")
            
            if i % 10 == 0 or i == total:
                print(f"进度: {i}/{total}，当前存活 {len(alive)} 个")
    
    # 按延迟排序
    if SORT_BY_LATENCY:
        alive.sort(key=lambda x: x[1])
    
    alive_proxies = [proxy for proxy, _ in alive]
    if alive:
        avg_latency = sum(lat for _, lat in alive) / len(alive)
        print(f"测速完成：存活 {len(alive_proxies)}/{total} 个节点，平均延迟 {avg_latency:.1f} ms")
    else:
        print("测速完成：无存活节点")
    
    return alive_proxies

# ---------- 配置构建和清理 ----------
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

    all_proxies = merge_proxies(all_proxies)
    print(f"去重后节点数: {len(all_proxies)}")

    alive_proxies = filter_alive_proxies(all_proxies)
    if not alive_proxies:
        print("没有存活节点，退出", file=sys.stderr)
        sys.exit(1)

    alive_names = {p['name'] for p in alive_proxies}

    if base_config:
        final_config = copy.deepcopy(base_config)
        final_config['proxies'] = alive_proxies
        final_config['proxy-groups'] = clean_proxy_groups(final_config.get('proxy-groups', []), alive_names)

        target_idx, target_name = find_target_group(final_config)
        if target_idx is not None:
            target_group = final_config['proxy-groups'][target_idx]
            target_group['type'] = 'url-test'
            target_group['url'] = TEST_URL
            target_group['interval'] = 300
            target_group['tolerance'] = 50
            target_group['proxies'] = list(alive_names)
            print(f"已将组 '{target_name}' 转换为 url-test，包含 {len(alive_names)} 个节点")
        else:
            auto_group = {
                "name": "AUTO",
                "type": "url-test",
                "url": TEST_URL,
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
                    "url": TEST_URL,
                    "interval": 300,
                    "tolerance": 50,
                    "proxies": list(alive_names)
                }
            ],
            "rules": ["MATCH,AUTO"]
        }

    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("已生成合并配置: clash/merged.yaml")
    if not ENABLE_HTTP_TEST:
        print("警告：当前未启用 HTTP 代理测速，结果可能含有实际不可用的节点。若要更精确过滤，请安装依赖并设置 ENABLE_HTTP_TEST = True")
    else:
        print("说明：已对 HTTP/SOCKS5 类型节点执行真实 HTTP 请求测速；对于 Trojan/Vless/VMess 节点仅做 TCP 检测，实际可用性请依赖 Clash 的 url-test 组。")

if __name__ == "__main__":
    main()
