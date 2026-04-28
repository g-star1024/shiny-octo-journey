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

def find_proxy_group_name(config):
    """
    从配置中智能找到应该放置所有节点的代理组名称。
    优先选择 type 为 'select' 且名称常见于出口代理组（如 PROXY, ALL, GLOBAL, 代理, 节点选择等）。
    如果找不到，返回 None。
    """
    proxy_groups = config.get('proxy-groups', [])
    if not proxy_groups:
        return None

    # 常见的出口组名称
    common_names = ['PROXY', 'ALL', 'GLOBAL', '选择', '节点选择', 'Proxy', 'global', 'proxy']
    for group in proxy_groups:
        if group.get('type') == 'select':
            group_name = group.get('name')
            if group_name in common_names:
                return group_name
    # 如果没找到常见名称，返回第一个 select 组的名称
    for group in proxy_groups:
        if group.get('type') == 'select':
            return group.get('name')
    # 如果没有 select 组，返回第一个组的名称（可以是任何类型）
    return proxy_groups[0].get('name')

def main():
    all_proxies = []
    # 保存第一个有效的完整配置（包含 proxy-groups 和 rules）
    base_config = None

    # 1. 下载所有配置，收集所有 proxies
    for url in URLS:
        print(f"Processing {url}")
        config = download_yaml(url)
        if not config:
            continue
        # 收集 proxies
        proxies = config.get('proxies')
        if proxies and isinstance(proxies, list):
            all_proxies.extend(proxies)
        # 选取第一个包含 proxy-groups 和 rules 的配置作为基础模板
        if base_config is None and config.get('proxy-groups') and config.get('rules'):
            base_config = config
            print(f"Using base config from {url}")

    if not all_proxies:
        print("No proxies found, exiting", file=sys.stderr)
        sys.exit(1)

    # 去重
    all_proxies = merge_proxies(all_proxies)
    print(f"Total unique proxies: {len(all_proxies)}")

    # 2. 构建最终配置
    if base_config:
        # 复制基础配置（深拷贝避免修改原数据）
        import copy
        final_config = copy.deepcopy(base_config)
        # 替换 proxies 列表为合并后的节点
        final_config['proxies'] = all_proxies

        # 找到应该包含所有节点的代理组名称
        target_group_name = find_proxy_group_name(base_config)
        if target_group_name:
            # 更新该组中的 proxies 列表为所有节点名称
            for group in final_config.get('proxy-groups', []):
                if group.get('name') == target_group_name:
                    # 保留组中其他原有配置（如 url-test 的 tolerance 等），只替换 proxies 列表
                    group['proxies'] = [p['name'] for p in all_proxies]
                    print(f"Updated group '{target_group_name}' with {len(all_proxies)} proxies")
                    break
            else:
                # 理论上不应该找不到，但万一找不到就创建一个新组
                print(f"Warning: target group '{target_group_name}' not found in proxy-groups", file=sys.stderr)
                default_group = {
                    "name": "ALL",
                    "type": "select",
                    "proxies": [p['name'] for p in all_proxies]
                }
                final_config['proxy-groups'].append(default_group)
                # 同时修改 rules 中最后的 MATCH 策略指向新组
                # 找到最后一个 MATCH 规则并替换
                for i, rule in enumerate(final_config.get('rules', [])):
                    if rule.startswith('MATCH,'):
                        final_config['rules'][i] = f"MATCH,ALL"
                        break
                else:
                    final_config['rules'].append("MATCH,ALL")
        else:
            # 没有找到合适的组，创建默认配置
            print("No suitable proxy group found, creating default groups", file=sys.stderr)
            final_config['proxy-groups'] = [{
                "name": "ALL",
                "type": "select",
                "proxies": [p['name'] for p in all_proxies]
            }]
            final_config['rules'] = ["MATCH,ALL"]
    else:
        # 没有任何配置包含 proxy-groups 和 rules，创建默认配置
        print("No base config with proxy-groups and rules found, using default config", file=sys.stderr)
        default_config = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": True,
            "mode": "rule",
            "log-level": "info",
            "external-controller": "0.0.0.0:9090",
            "proxies": all_proxies,
            "proxy-groups": [{
                "name": "ALL",
                "type": "select",
                "proxies": [p['name'] for p in all_proxies]
            }],
            "rules": ["MATCH,ALL"]
        }
        final_config = default_config

    # 3. 写入文件
    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("Merged config written to clash/merged.yaml")

if __name__ == "__main__":
    main()
