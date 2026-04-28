#!/usr/bin/env python3
import requests
import yaml
import sys
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy

# 所有订阅源 URL（保持不变）
URLS = [ ... ]  # 你原来的那些链接

HEADERS = {"User-Agent": "Mozilla/5.0"}

TCP_TIMEOUT = 3
MAX_WORKERS = 20

def download_yaml(url):
    # 同上，省略...

def merge_proxies(all_proxies):
    # 同上，省略...

def check_proxy(proxy):
    # 同上，省略...

def filter_alive_proxies(proxies):
    # 同上，省略...

def find_target_group(config):
    # 同上，省略...

def clean_proxy_groups(proxy_groups, alive_names):
    """
    遍历所有代理组，过滤掉 proxies 列表中失效的节点名称。
    保留内置策略（如 DIRECT, REJECT, 以及以 . 或 + 开头的策略组引用）和仍存活的节点。
    """
    # 内置策略或特殊标识（通常大写，也可能有小写）
    builtin_strategies = {'DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'GLOBAL'}
    cleaned_groups = []
    for group in proxy_groups:
        if 'proxies' not in group:
            cleaned_groups.append(group)
            continue
        original = group['proxies']
        filtered = []
        for item in original:
            # 如果 item 是内置策略 或 以 . + 开头（Clash 中表示引用其他组），则保留
            if item in builtin_strategies or item.startswith('.') or item.startswith('+'):
                filtered.append(item)
            elif item in alive_names:
                filtered.append(item)
            else:
                print(f"Removing dead node '{item}' from group '{group.get('name')}'", file=sys.stderr)
        group['proxies'] = filtered
        cleaned_groups.append(group)
    return cleaned_groups

def main():
    all_proxies = []
    base_config = None

    # 下载所有配置，收集所有 proxies...
    # （和之前一样，略）

    # 去重
    all_proxies = merge_proxies(all_proxies)
    print(f"Total unique proxies before filtering: {len(all_proxies)}")

    # 过滤存活节点
    alive_proxies = filter_alive_proxies(all_proxies)
    if not alive_proxies:
        sys.exit(1)

    alive_names = {p['name'] for p in alive_proxies}

    # 构建最终配置
    if base_config:
        final_config = copy.deepcopy(base_config)
        final_config['proxies'] = alive_proxies

        # 清理所有代理组中失效的节点引用
        final_config['proxy-groups'] = clean_proxy_groups(final_config.get('proxy-groups', []), alive_names)

        # 将目标组转换为 url-test（并再次确保它的 proxies 列表正确）
        target_idx, target_name = find_target_group(final_config)
        if target_idx is not None:
            target_group = final_config['proxy-groups'][target_idx]
            target_group['type'] = 'url-test'
            target_group['url'] = 'http://www.gstatic.com/generate_204'
            target_group['interval'] = 300
            target_group['tolerance'] = 50
            target_group['proxies'] = list(alive_names)   # 直接使用所有存活节点名
            print(f"Converted group '{target_name}' to url-test with {len(alive_names)} proxies")
        else:
            # 没有目标组就新增一个
            auto_group = {
                "name": "AUTO",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": list(alive_names)
            }
            final_config.setdefault('proxy-groups', []).append(auto_group)
            # 修改最后一条 MATCH 规则
            rules = final_config.get('rules', [])
            for i, rule in enumerate(rules):
                if rule.startswith('MATCH,'):
                    rules[i] = "MATCH,AUTO"
                    break
    else:
        # 无基础配置时创建默认配置
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

    # 写入文件
    import os
    os.makedirs("clash", exist_ok=True)
    with open("clash/merged.yaml", "w", encoding="utf-8") as f:
        yaml.dump(final_config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print("Merged config written to clash/merged.yaml")

if __name__ == "__main__":
    main()
