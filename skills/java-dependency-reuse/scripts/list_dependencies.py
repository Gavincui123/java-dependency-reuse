#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析 pom.xml，列出 Maven 直接依赖，并定位本地仓库中的 jar 文件。

用途：写 Java 代码前先盘点项目依赖里"已经有什么"，避免重复造轮子。
跨平台（macOS/Linux/Windows）：本地仓库路径自动发现，见 maven_env.detect_local_repo。
只解析当前 pom 的 <dependencies>（含 properties 变量解析）；需要全量传递依赖时加 --transitive。

用法示例：
  python3 list_dependencies.py
  python3 list_dependencies.py --pom /path/to/pom.xml
  python3 list_dependencies.py --local-repo D:/maven/repo          # 显式覆盖自动发现
  python3 list_dependencies.py --transitive                        # mvn dependency:list 全量传递依赖
  python3 list_dependencies.py --detect-via-mvn                    # 允许调用 mvn 权威探测仓库路径
"""
import argparse
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maven_env as me  # noqa: E402


def load_pom(path: str):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"pom.xml 不存在: {path}")
    return ET.parse(path).getroot()


def resolve_properties(root) -> dict:
    props = {}
    node = me.xml_find(root, "properties")
    if node is not None:
        for child in node:
            if child.text:
                props[me.localname(child.tag)] = child.text.strip()
    return props


def resolve_value(value: str, props: dict) -> str:
    """解析 ${...} 变量引用；无法解析时保留原样。"""
    if not value:
        return ""
    if value.startswith("${") and value.endswith("}"):
        return props.get(value[2:-1], value)
    return value


def jar_path(local_repo: str, gid: str, aid: str, version: str, packaging: str) -> tuple:
    """返回 (jar 路径, 是否存在于本地仓库)。"""
    if packaging == "pom":
        return None, False
    base = os.path.join(
        local_repo,
        gid.replace(".", os.sep),
        aid.replace(".", os.sep),
        version,
    )
    jar = os.path.join(base, f"{aid}-{version}.jar")
    if os.path.isfile(jar):
        return jar, True
    # 兜底：同目录下非 sources/javadoc 的 artifact（classifier 场景）
    if os.path.isdir(base):
        for name in sorted(os.listdir(base)):
            if name.endswith(".jar") and not name.endswith(("-sources.jar", "-javadoc.jar")):
                return os.path.join(base, name), True
    return jar, False


def parse_dependencies(root, props: dict) -> list:
    deps_node = me.xml_find(root, "dependencies")
    result = []
    if deps_node is None:
        return result
    for dep in me.xml_findall(deps_node, "dependency"):
        gid = resolve_value(me.xml_text(dep, "groupId"), props)
        aid = resolve_value(me.xml_text(dep, "artifactId"), props)
        version = resolve_value(me.xml_text(dep, "version"), props)
        scope = resolve_value(me.xml_text(dep, "scope"), props) or "compile"
        packaging = resolve_value(me.xml_text(dep, "type"), props) or "jar"
        optional = resolve_value(me.xml_text(dep, "optional"), props)
        if not gid or not aid:
            continue
        result.append(
            {"gid": gid, "aid": aid, "version": version, "scope": scope,
             "type": packaging, "optional": optional}
        )
    return result


def run_mvn_dependency_list(pom: str) -> list:
    """用 mvn dependency:list 获取全量传递依赖。"""
    mvn = me.find_maven()
    if not mvn:
        print("[提示] 未找到 mvn（PATH/MAVEN_HOME/M2_HOME 均无），仅显示直接依赖。", file=sys.stderr)
        return []
    try:
        code, out, err = me.run_cmd(
            mvn,
            ["-q", "-f", pom, "dependency:list", "-DincludeScope=compile,runtime"],
            timeout=180,
        )
    except Exception as exc:  # TimeoutExpired 等
        print(f"[提示] mvn dependency:list 执行失败（{exc}），仅显示直接依赖。", file=sys.stderr)
        return []
    result = []
    for line in out.splitlines():
        line = line.strip()
        # 形如: [INFO]    org.springframework:spring-core:jar:6.1.6:compile
        if not line.startswith("["):
            continue
        body = line.split("]", 1)[-1].strip()
        if ":" not in body:
            continue
        parts = body.split(":")
        if len(parts) < 3:
            continue
        gid, aid = parts[0], parts[1]
        version, scope = "", "compile"
        tail = parts[2:]
        for idx, part in enumerate(tail):
            if part in ("jar", "pom", "war", "bundle"):
                continue
            if idx == len(tail) - 1 and part in ("compile", "runtime", "test", "provided", "system"):
                scope = part
            elif not version:
                version = part
        if gid and aid:
            result.append({"gid": gid, "aid": aid, "version": version, "scope": scope,
                           "type": "jar", "optional": ""})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pom", default=None, help="pom.xml 路径；缺省时从当前目录向上查找")
    parser.add_argument("--local-repo", default=None, help="本地 Maven 仓库路径；缺省按 settings.xml/环境变量/默认位置自动发现")
    parser.add_argument("--detect-via-mvn", action="store_true", help="自动发现失败时允许调用 mvn help:evaluate 权威探测（较慢）")
    parser.add_argument("--transitive", action="store_true", help="同时执行 mvn dependency:list 列出全量传递依赖（需要 mvn）")
    args = parser.parse_args()

    try:
        pom = args.pom or me.find_pom(os.getcwd())
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    local_repo, repo_source = me.detect_local_repo(args.local_repo, via_mvn=args.detect_via_mvn)

    root = load_pom(pom)
    props = resolve_properties(root)
    deps = parse_dependencies(root, props)

    parent = me.xml_find(root, "parent")
    gid = resolve_value(me.xml_text(root, "groupId") or me.xml_text(parent, "groupId"), props)
    aid = me.xml_text(root, "artifactId") or os.path.basename(os.path.dirname(pom))
    version = resolve_value(me.xml_text(root, "version") or me.xml_text(parent, "version"), props)
    print(f"项目: {gid}:{aid}:{version}")
    print(f"POM : {pom}")
    print(f"本地仓库: {local_repo}")
    print(f"仓库来源: {repo_source}")
    if not os.path.isdir(local_repo):
        print(f"[警告] 本地仓库目录不存在：{local_repo}（可用 --local-repo 指定，或检查 settings.xml）", file=sys.stderr)
    print(f"直接依赖数: {len(deps)}\n")

    if not deps:
        print("[提示] 当前 pom.xml 未声明直接依赖。若依赖在父 POM 管理，请对子模块执行，或使用 --transitive。")

    print(f"{'坐标 (groupId:artifactId:version)':<72} {'scope':<10} {'jar':<5} 路径")
    print("-" * 140)
    for d in sorted(deps, key=lambda x: (x["gid"], x["aid"])):
        coords = f"{d['gid']}:{d['aid']}:{d['version']}" if d["version"] else f"{d['gid']}:{d['aid']}:(版本由父POM管理)"
        path, exists = jar_path(local_repo, d["gid"], d["aid"], d["version"], d["type"])
        print(f"{coords:<72} {d['scope']:<10} {'有' if exists else '缺':<5} {path or ''}")

    if args.transitive:
        print("\n[传递依赖] 运行 mvn dependency:list ...")
        transitives = run_mvn_dependency_list(pom)
        print(f"传递依赖解析数: {len(transitives)}")
        for d in sorted(transitives, key=lambda x: (x["gid"], x["aid"])):
            print(f"  {d['gid']}:{d['aid']}:{d['version']}  ({d['scope']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
