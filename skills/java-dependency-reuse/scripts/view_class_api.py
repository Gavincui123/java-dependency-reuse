#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看 Maven 依赖 jar 中某个类的真实 API 签名（基于 javap，JDK 自带）。

写代码前用本脚本核对依赖类的真实方法签名，避免凭记忆写错 API。
跨平台：javap 从 PATH / JAVA_HOME 自动发现；本地仓库路径自动发现。
可显示继承链上父类的公共方法（--super 递归层数）。

用法示例：
  python3 view_class_api.py --class org.apache.commons.lang3.StringUtils --pom /path/to/pom.xml
  python3 view_class_api.py --class org.springframework.util.StringUtils --pom /path/to/pom.xml --super 2
  python3 view_class_api.py --class com.fasterxml.jackson.databind.ObjectMapper --jars /path/to/jackson-databind.jar
"""
import argparse
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maven_env as me  # noqa: E402
import list_dependencies as ld  # noqa: E402
from search_class_in_jars import load_map_index  # noqa: E402


def collect_jars(pom: str, local_repo: str) -> list:
    root = ld.load_pom(pom)
    props = ld.resolve_properties(root)
    jars = []
    for d in ld.parse_dependencies(root, props):
        path, exists = ld.jar_path(local_repo, d["gid"], d["aid"], d["version"], d["type"])
        if exists and path:
            jars.append(path)
    return jars


def find_jar_for_class(jars: list, fqcn: str) -> str:
    """在 jar 列表中定位包含该类的 jar。"""
    entry = fqcn.replace(".", "/") + ".class"
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as zf:
                if entry in set(zf.namelist()):
                    return jar
        except (zipfile.BadZipFile, OSError):
            continue
    return ""


def javap(javap_exe: str, classpath: str, fqcn: str) -> str:
    """调用 javap -public 显示公共 API；失败时回退到 -protected。"""
    code, out, err = me.run_cmd(javap_exe, ["-public", "-classpath", classpath, fqcn])
    if code != 0:
        code, out, err = me.run_cmd(javap_exe, ["-protected", "-classpath", classpath, fqcn])
    if code != 0:
        return f"(javap 失败: {err.strip() or out.strip()})"
    return out.rstrip()


def resolve_parents(output: str) -> list:
    """从 javap 输出的类声明中提取父类/接口，供 --super 递归。"""
    parents = []
    for line in output.splitlines():
        stripped = line.strip()
        is_type = stripped.startswith(("public class ", "class ", "final class ", "public final class ",
                                       "public abstract class ", "public interface ", "interface "))
        if not is_type:
            continue
        for keyword in ("extends ", "implements "):
            idx = stripped.find(keyword)
            if idx != -1:
                rest = stripped[idx + len(keyword):].split("{")[0].strip().rstrip(";")
                for name in rest.split(","):
                    name = name.strip()
                    if name and name != "Object":
                        parents.append(name)
    return parents


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--class", dest="class_name", required=True, help="完整类名，如 org.apache.commons.lang3.StringUtils")
    parser.add_argument("--pom", default=None, help="pom.xml 路径；缺省时从当前目录向上查找")
    parser.add_argument("--local-repo", default=None, help="本地 Maven 仓库路径；缺省自动发现")
    parser.add_argument("--jars", default=None, help="直接指定 jar 列表（逗号分隔），与 --pom 二选一")
    parser.add_argument("--map-dir", default=None, help="依赖地图目录；缺省为 pom 同级 .dep-map/")
    parser.add_argument("--no-map", action="store_true", help="不使用地图索引定位类")
    parser.add_argument("--super", type=int, default=0, help="额外递归显示继承链父类/接口的公共方法层数（默认 0）")
    args = parser.parse_args()

    javap_exe = me.find_javap()
    if not javap_exe:
        print("错误: 未找到 javap。请确认已安装 JDK 并加入 PATH，或设置 JAVA_HOME 环境变量。", file=sys.stderr)
        return 1

    if args.jars:
        jars = [p.strip() for p in args.jars.split(",") if p.strip()]
    else:
        try:
            pom = args.pom or me.find_pom(os.getcwd())
        except FileNotFoundError as exc:
            print(f"错误: {exc}", file=sys.stderr)
            return 1
        local_repo, _ = me.detect_local_repo(args.local_repo)
        jars = collect_jars(pom, local_repo)

    if not jars:
        print("没有可用的依赖 jar（依赖未下载到本地仓库，或仓库路径不对）。", file=sys.stderr)
        return 1

    # Windows classpath 分隔符是分号，其余平台是冒号
    sep = ";" if os.name == "nt" else ":"
    classpath = sep.join(jars)

    def locate(fqcn):
        """先查 L2 地图索引（毫秒），未命中再遍历 jar；返回类所在 jar。"""
        if not args.no_map and not args.jars:
            index, _ = load_map_index(pom, args.map_dir)
            hits = index.get(fqcn)
            if hits:
                return hits[0]
        return find_jar_for_class(jars, fqcn)

    if args.jars:
        jar = find_jar_for_class(jars, args.class_name)
    else:
        jar = locate(args.class_name)
    if not jar:
        print(f"在 {len(jars)} 个依赖 jar 中未找到类 {args.class_name}。", file=sys.stderr)
        print("可先运行 search_class_in_jars.py 确认类是否真的存在于依赖中。", file=sys.stderr)
        return 1

    print(f"类: {args.class_name}\n来自 jar: {jar}\n")
    output = javap(javap_exe, classpath, args.class_name)
    print(output)
    print()

    seen = {args.class_name}
    queue = resolve_parents(output)
    depth = 0
    while queue and depth < args.super:
        depth += 1
        next_queue = []
        for parent in queue:
            if parent in seen:
                continue
            seen.add(parent)
            pjar = locate(parent)
            if not pjar:
                print(f"[父类/接口 {parent}] 不在当前依赖 jar 中，跳过")
                continue
            print(f"--- 父类/接口 {parent} (来自 {pjar}) ---")
            pout = javap(javap_exe, classpath, parent)
            print(pout)
            print()
            next_queue.extend(resolve_parents(pout))
        queue = next_queue

    if args.super == 0:
        print("[提示] 若需查看父类/接口的方法，加 --super 1 或更大。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
