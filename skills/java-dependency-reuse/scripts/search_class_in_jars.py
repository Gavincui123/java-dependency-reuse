#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在 Maven 依赖 jar 中搜索类，回答"这个类/这个工具在哪个依赖里"。

优先使用 build_dependency_map.py 生成的 L2 索引（毫秒级，无需扫 jar）；
地图缺失或未覆盖的依赖自动回退实时扫描，保证结果始终正确。
跨平台：本地仓库路径自动发现（见 maven_env.py），也可用 --local-repo 覆盖。

用法示例：
  python3 search_class_in_jars.py --class StringUtils --pom /path/to/pom.xml
  python3 search_class_in_jars.py --class org.apache.commons.lang3.StringUtils --pom /path/to/pom.xml
  python3 search_class_in_jars.py --class org.apache.commons.lang3 --pom /path/to/pom.xml   # 包前缀
  python3 search_class_in_jars.py --class StringUtils --no-map                               # 强制实时扫 jar
  python3 search_class_in_jars.py --class StringUtils --jars C:/lib/a.jar,D:/lib/b.jar

匹配规则：精确类名(EXACT) > 简单类名(SIMPLE) > 包前缀(PREFIX)。
"""
import argparse
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maven_env as me  # noqa: E402
import list_dependencies as ld  # noqa: E402
from build_dependency_map import DEFAULT_MAP_DIRNAME, L2_NAME  # noqa: E402


def collect_jars(pom: str, local_repo: str) -> list:
    """返回 pom 直接依赖在本地仓库中实际存在的 jar 路径列表。"""
    root = ld.load_pom(pom)
    props = ld.resolve_properties(root)
    jars = []
    for d in ld.parse_dependencies(root, props):
        path, exists = ld.jar_path(local_repo, d["gid"], d["aid"], d["version"], d["type"])
        if exists and path:
            jars.append(path)
    return jars


def match_target(fqcn: str, target: str, simple: str):
    """返回匹配类型 EXACT/SIMPLE/PREFIX/None。target/simple 已转为斜杠路径形式。"""
    path_name = fqcn.replace(".", "/")
    if path_name == target:
        return "EXACT"
    if path_name.endswith("/" + simple) or path_name == simple:
        return "SIMPLE"
    if path_name.startswith(target) and path_name != target and "/" in path_name:
        return "PREFIX"
    return None


def scan(jars: list, target: str) -> list:
    """实时扫描 jar，返回 [(匹配类型, FQCN, jar_path)]。"""
    target = target.replace("\\", "/").replace(".", "/").strip("/")
    simple = target.rsplit("/", 1)[-1]
    matches = []
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as zf:
                for name in zf.namelist():
                    if not name.endswith(".class"):
                        continue
                    if name.startswith("META-INF/") or name.endswith(("module-info.class", "package-info.class")):
                        continue
                    fqcn = name[:-6].replace("/", ".")
                    if "$" in fqcn:
                        continue
                    kind = match_target(fqcn, target, simple)
                    if kind:
                        matches.append((kind, fqcn, jar))
        except (zipfile.BadZipFile, OSError) as exc:
            print(f"[警告] 跳过无法读取的 jar: {jar} ({exc})", file=sys.stderr)
    return matches


def load_map_index(pom: str, map_dir: str):
    """加载 L2 扁平类索引，返回 (fqcn->[jars], 已覆盖 jar 集合)。"""
    path = os.path.join(map_dir or os.path.join(os.path.dirname(os.path.abspath(pom)), DEFAULT_MAP_DIRNAME), L2_NAME)
    if not os.path.isfile(path):
        return {}, set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}, set()
    index = data.get("class_index", {})
    covered = {dep.get("jar") for dep in data.get("dependencies", {}).values() if dep.get("jar")}
    return index, covered


def scan_index(index: dict, target: str) -> list:
    """在内存索引中匹配，返回 [(匹配类型, FQCN, jar)]。"""
    target = target.replace("\\", "/").replace(".", "/").strip("/")
    simple = target.rsplit("/", 1)[-1]
    matches = []
    for fqcn, jars in index.items():
        kind = match_target(fqcn, target, simple)
        if kind:
            for jar in jars:
                matches.append((kind, fqcn, jar))
    return matches


def render(matches: list) -> str:
    if not matches:
        return "未在任何依赖 jar 中找到匹配类。可以手写，但请先核对 references/common_java_libraries.md 中的常见场景。"
    # 去重并按匹配优先级排序
    seen, rows = set(), []
    order = {"EXACT": 0, "SIMPLE": 1, "PREFIX": 2}
    for kind, fqcn, jar in sorted(matches, key=lambda x: (order.get(x[0], 9), x[1])):
        key = (kind, fqcn, jar)
        if key in seen:
            continue
        seen.add(key)
        rows.append(f"[{kind}] {fqcn}\n        位于 {jar}")
    return f"找到 {len(rows)} 个匹配：\n\n" + "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="class_name", required=True, help="类名/完整类名/包前缀")
    parser.add_argument("--pom", default=None, help="pom.xml 路径；缺省时从当前目录向上查找")
    parser.add_argument("--local-repo", default=None, help="本地 Maven 仓库路径；缺省自动发现")
    parser.add_argument("--map-dir", default=None, help="依赖地图目录；缺省为 pom 同级 .dep-map/")
    parser.add_argument("--no-map", action="store_true", help="不使用地图索引，强制实时扫描 jar")
    parser.add_argument("--jars", default=None, help="直接指定 jar 列表（逗号分隔），与 --pom 二选一")
    args = parser.parse_args()

    if args.jars:
        jars = [p.strip() for p in args.jars.split(",") if p.strip()]
        print(f"扫描范围: 指定 jar 列表 ({len(jars)} 个)")
        matches = scan(jars, args.class_name)
    else:
        try:
            pom = args.pom or me.find_pom(os.getcwd())
        except FileNotFoundError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1
        local_repo, _ = me.detect_local_repo(args.local_repo)
        jars = collect_jars(pom, local_repo)
        if not jars:
            print("没有可扫描的 jar（依赖未下载到本地仓库、仓库路径不对或 pom 无直接依赖）。", file=sys.stderr)
            print("可先用 list_dependencies.py 确认仓库路径与依赖状态。", file=sys.stderr)
            return 1

        matches = []
        if not args.no_map:
            index, covered = load_map_index(pom, args.map_dir)
            indexed_jars = [j for j in jars if j in covered]
            live_jars = [j for j in jars if j not in covered]
            if index:
                matches.extend(scan_index(index, args.class_name))
            if live_jars:
                print(f"[提示] {len(live_jars)} 个依赖未被地图覆盖（地图缺失或依赖更新），已实时扫描；"
                      f"可运行 build_dependency_map.py 更新地图。", file=sys.stderr)
                matches.extend(scan(live_jars, args.class_name))
            mode = f"地图索引覆盖 {len(indexed_jars)} 个 jar" + (f"，实时扫描 {len(live_jars)} 个" if live_jars else "")
            print(f"扫描范围: pom 直接依赖 ({len(jars)} 个 jar)，{mode}")
        else:
            print(f"扫描范围: pom 直接依赖 ({len(jars)} 个 jar)，已禁用地图、实时扫描")
            matches = scan(jars, args.class_name)

    print(render(matches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
