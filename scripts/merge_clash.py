#!/usr/bin/env python3
import requests
import yaml
import sys
from collections import OrderedDict

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def download_yaml(url):
    """下载并解析 YAML，返回 parsed dict，失败返回 None"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        # 有些源可能返回的不是严格 YAML，尝试直接解析
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
        # 确保 proxy 是一个字典且有 name 字段
        if not isinstance(proxy, dict) or 'name' not in proxy:
            continue
        name = proxy['name']
        if name not in seen:
            seen.add(name)
            merged.append(proxy)
    return merged

def main():
    all_proxies = []
    # 用于提取第一个有效的 rules 和 proxy-groups（可选）
    first_valid_config = None

    for url in URLS:
        print(f"Processing {url}")
        config = download_yaml(url)
        if not config:
            continue
        # 提取 proxies
        proxies = config.get('proxies')
        if proxies and isinstance(proxies, list):
            all_proxies.extend(proxies)
        # 记录第一个非空配置，用于保留其部分顶层字段（可选）
        if first_valid_config is None and proxies:
            first_valid_config = config

    if not all_proxies:
        print("No proxies found, exiting", file=sys.stderr)
        sys.exit(1)

    # 去重
    all_proxies = merge_proxies(all_proxies)
    print(f"Total unique proxies: {len(all_proxies)}")

    # 构建最终的 Clash 配置
    # 从第一个有效配置中获取一些顶层默认值，或使用系统默认
    default_config = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "external-controller": "0.0.0.0:9090",
    }
    # 如果第一个配置中有这些字段，可以覆盖（但这里简单使用默认）
    final_config = default_config.copy()
    final_config["proxies"] = all_proxies

    # 构建 proxy-groups，包含所有节点
    proxy_names = [p['name'] for p in all_proxies]
    final_config["proxy-groups"] = [
        {
            "name": "ALL",
            "type": "select",
            "proxies": proxy_names
        }
    ]

    # 简单规则：所有流量走 ALL 组
    final_config["rules"] = [
        "MATCH,ALL"
    ]

    # 可选：保留原始配置中的规则和组（但更容易出错，先使用简单通用方案）

    # 确保输出目录存在
    import os
    os.makedirs("clash", exist_ok=True)

    # 写入 YAML 文件
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("Merged config written to clash/merged.yaml")

if __name__ == "__main__":
    main()
