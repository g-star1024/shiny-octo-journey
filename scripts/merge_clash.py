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

def find_target_group(config):
    """
    找到应该被转换为 url-test 的代理组。
    优先选择 type='select' 且名称常见于出口组（PROXY, ALL, GLOBAL, 选择 等）。
    如果没有则选择第一个 select 组，再没有则选择第一个代理组。
    返回 (group_index, group_name)
    """
    proxy_groups = config.get('proxy-groups', [])
    if not proxy_groups:
        return None, None

    common_names = ['PROXY', 'ALL', 'GLOBAL', '选择', '节点选择', 'Proxy', 'global', 'proxy']
    # 优先按名称匹配
    for idx, group in enumerate(proxy_groups):
        if group.get('type') == 'select' and group.get('name') in common_names:
            return idx, group.get('name')
    # 其次找第一个 select 组
    for idx, group in enumerate(proxy_groups):
        if group.get('type') == 'select':
            return idx, group.get('name')
    # 最后只能拿第一个组
    return 0, proxy_groups[0].get('name')

def main():
    all_proxies = []
    base_config = None

    # 1. 下载所有配置，收集 proxies
    for url in URLS:
        print(f"Processing {url}")
        config = download_yaml(url)
        if not config:
            continue
        proxies = config.get('proxies')
        if proxies and isinstance(proxies, list):
            all_proxies.extend(proxies)
        # 选择第一个包含 proxy-groups 和 rules 的配置作为基础模板
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
        import copy
        final_config = copy.deepcopy(base_config)
        # 替换 proxies
        final_config['proxies'] = all_proxies

        # 找到目标组并转换为 url-test
        target_idx, target_name = find_target_group(final_config)
        if target_idx is not None:
            target_group = final_config['proxy-groups'][target_idx]
            # 保留原有组的部分字段（如 name, 其他属性），但修改 type 为 url-test
            # 添加 url-test 必需的字段
            target_group['type'] = 'url-test'
            target_group['url'] = 'http://www.gstatic.com/generate_204'  # 测速 URL
            target_group['interval'] = 300  # 测试间隔（秒）
            target_group['tolerance'] = 50  # 延迟容差（ms），50以内认为一样快
            # 将 proxies 列表设置为所有节点名
            proxy_names = [p['name'] for p in all_proxies]
            target_group['proxies'] = proxy_names
            # 移除可能冲突的字段（如旧的 proxies 已经在上面被覆盖）
            print(f"Converted group '{target_name}' to url-test with {len(proxy_names)} proxies")
        else:
            print("No suitable proxy group found, creating a new url-test group", file=sys.stderr)
            # 如果没有找到任何组，则添加一个 url-test 组
            proxy_names = [p['name'] for p in all_proxies]
            auto_group = {
                "name": "AUTO",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": proxy_names
            }
            final_config.setdefault('proxy-groups', []).append(auto_group)
            # 同时修改 rules 中最后的 MATCH 指向这个新组
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
        # 没有基础配置，创建默认配置并加入 url-test
        print("No base config found, creating default config with url-test", file=sys.stderr)
        proxy_names = [p['name'] for p in all_proxies]
        final_config = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": True,
            "mode": "rule",
            "log-level": "info",
            "external-controller": "0.0.0.0:9090",
            "proxies": all_proxies,
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

    # 3. 写入文件
    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("Merged config written to clash/merged.yaml")

if __name__ == "__main__":
    main()
