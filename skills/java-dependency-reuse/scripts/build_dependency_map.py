#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构建/增量更新 Maven 依赖地图（L1 能力地图 + L2 全量类索引）。

一次扫描、反复复用：写代码前先读 L1 地图（.dep-map/dependency-map.md）知道项目有哪些能力；
search_class_in_jars.py 自动使用 L2 索引（dependency-map.json）做毫秒级类查找，无需每次扫 jar。
依赖变化时按内容指纹增量更新，也可 --refresh 强制全量重建。跨平台，仅用 Python 标准库。

用法示例：
  python3 build_dependency_map.py                       # 自动找 pom，增量构建到项目内 .dep-map/
  python3 build_dependency_map.py --pom /path/pom.xml --refresh
  python3 build_dependency_map.py --transitive          # 含 mvn dependency:list 的传递依赖
  python3 build_dependency_map.py --map-dir /other/dir  # 自定义地图输出目录
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import maven_env as me  # noqa: E402
import list_dependencies as ld  # noqa: E402

MAP_VERSION = 1
DEFAULT_MAP_DIRNAME = ".dep-map"
L1_NAME = "dependency-map.md"
L2_NAME = "dependency-map.json"
MAX_KEY_CLASSES = 20  # L1 每个依赖最多列出的关键类数

# 常见依赖的能力域与关键类（gid:aid 匹配，关键类写简单名，构建时校验其真实存在）
KNOWN_LIBS = {
    "org.apache.commons:commons-lang3": {
        "domains": ["字符串", "数组", "对象判空", "数学/随机", "异常"],
        "keys": ["StringUtils", "ArrayUtils", "ObjectUtils", "BooleanUtils", "Validate",
                 "ExceptionUtils", "RandomStringUtils", "Pair", "Triple", "ClassUtils",
                 "Convert", "NumberUtils", "CharSequenceUtils", "time.DurationFormatUtils"],
    },
    "org.apache.commons:commons-collections4": {
        "domains": ["集合工具", "多值Map", "Bag", "转换器"],
        "keys": ["CollectionUtils", "ListUtils", "MapUtils", "SetUtils", "MultiMap",
                 "ArrayListValuedHashMap", "PredicateUtils", "TransformerUtils"],
    },
    "commons-io:commons-io": {
        "domains": ["文件", "流IO", "文件名/编码"],
        "keys": ["FileUtils", "IOUtils", "FilenameUtils", "FileCopyUtils", "Charsets",
                 "LineIterator", "FileSystemUtils"],
    },
    "commons-codec:commons-codec": {
        "domains": ["摘要MD5/SHA", "Base64", "十六进制", "编解码"],
        "keys": ["DigestUtils", "Base64", "Hex", "Codec", "BinaryCodec", "UrlCodec"],
    },
    "com.google.guava:guava": {
        "domains": ["不可变集合", "集合工厂", "字符串切分", "缓存", "前置条件", "多值Map"],
        "keys": ["Lists", "Maps", "Sets", "ImmutableList", "ImmutableMap", "Splitter",
                 "Joiner", "Strings", "CharMatcher", "Preconditions", "CacheBuilder",
                 "Multimap", "ArrayListMultimap", "Optional", "Ordering", "Iterables"],
    },
    "cn.hutool:hutool-all": {
        "domains": ["一站式工具", "字符串/集合", "日期", "加密", "HTTP", "JSON", "文件", "Bean"],
        "keys": ["StrUtil", "CollUtil", "ObjectUtil", "DateUtil", "LocalDateTimeUtil",
                 "SecureUtil", "HttpUtil", "JSONUtil", "FileUtil", "BeanUtil", "Convert",
                 "IdUtil", "RandomUtil", "Assert", "IoUtil", "MapUtil", "NumUtil"],
    },
    "cn.hutool:hutool-core": {
        "domains": ["核心工具", "字符串/集合", "日期", "Bean", "类型转换"],
        "keys": ["StrUtil", "CollUtil", "ObjectUtil", "DateUtil", "BeanUtil", "Convert",
                 "IdUtil", "RandomUtil", "Assert", "ClassUtil", "ReflectUtil"],
    },
    "org.springframework:spring-core": {
        "domains": ["字符串/对象工具", "断言", "类型转换", "资源加载", "BeanUtils"],
        "keys": ["StringUtils", "ObjectUtils", "Assert", "CollectionUtils", "ClassUtils",
                 "BeanUtils", "ResolvableType", "ResourceUtils", "NestedExceptionUtils"],
    },
    "org.springframework:spring-beans": {
        "domains": ["Bean定义/拷贝", "BeanWrapper", "属性访问"],
        "keys": ["BeanUtils", "BeanWrapper", "PropertyAccessor", "BeanFactory"],
    },
    "org.springframework:spring-context": {
        "domains": ["容器上下文", "事件", "定时任务", "国际化"],
        "keys": ["ApplicationContext", "ApplicationEvent", "Scheduled", "Environment"],
    },
    "org.springframework:spring-web": {
        "domains": ["HTTP客户端", "Web工具", "URI构建"],
        "keys": ["RestTemplate", "WebClient", "UriComponentsBuilder", "HttpHeaders",
                 "MediaType", "WebUtils"],
    },
    "org.springframework:spring-jdbc": {
        "domains": ["JDBC模板", "事务/数据源"],
        "keys": ["JdbcTemplate", "NamedParameterJdbcTemplate", "RowMapper"],
    },
    "org.springframework:spring-tx": {
        "domains": ["事务管理"],
        "keys": ["TransactionTemplate", "PlatformTransactionManager", "Transactional"],
    },
    "com.fasterxml.jackson.core:jackson-databind": {
        "domains": ["JSON序列化/反序列化", "树模型", "绑定配置"],
        "keys": ["ObjectMapper", "JsonNode", "ObjectReader", "ObjectWriter",
                 "DeserializationFeature", "SerializationFeature", "JavaType"],
    },
    "com.fasterxml.jackson.core:jackson-core": {
        "domains": ["JSON流式解析/生成"],
        "keys": ["JsonFactory", "JsonParser", "JsonGenerator"],
    },
    "com.google.code.gson:gson": {
        "domains": ["JSON序列化/反序列化"],
        "keys": ["Gson", "JsonObject", "JsonArray", "TypeToken", "GsonBuilder"],
    },
    "com.alibaba:fastjson": {
        "domains": ["JSON序列化/反序列化"],
        "keys": ["JSON", "JSONObject", "JSONArray", "TypeReference"],
    },
    "com.alibaba.fastjson2:fastjson2": {
        "domains": ["JSON序列化/反序列化"],
        "keys": ["JSON", "JSONObject", "JSONArray", "TypeReference"],
    },
    "org.projectlombok:lombok": {
        "domains": ["注解式样板代码", "getter/setter/builder/log"],
        "keys": ["Data", "Builder", "Getter", "Setter", "Slf4j", "NoArgsConstructor",
                 "AllArgsConstructor", "RequiredArgsConstructor"],
    },
    "org.slf4j:slf4j-api": {
        "domains": ["日志门面"],
        "keys": ["Logger", "LoggerFactory", "MDC"],
    },
    "org.apache.httpcomponents.client5:httpclient5": {
        "domains": ["HTTP客户端"],
        "keys": ["CloseableHttpClient", "HttpClients", "HttpGet", "HttpPost", "RequestConfig"],
    },
    "org.apache.httpcomponents:httpclient": {
        "domains": ["HTTP客户端"],
        "keys": ["CloseableHttpClient", "HttpClients", "HttpGet", "HttpPost", "RequestConfig"],
    },
    "com.squareup.okhttp3:okhttp": {
        "domains": ["HTTP客户端"],
        "keys": ["OkHttpClient", "Request", "Response", "MediaType", "RequestBody"],
    },
    "org.mapstruct:mapstruct": {
        "domains": ["编译期Bean映射"],
        "keys": ["Mapper", "Mapping", "Mappings"],
    },
    "jakarta.validation:jakarta.validation-api": {
        "domains": ["参数校验注解"],
        "keys": ["Valid", "NotNull", "NotBlank", "Size", "Pattern"],
    },
    "javax.validation:validation-api": {
        "domains": ["参数校验注解"],
        "keys": ["Valid", "NotNull", "NotBlank", "Size", "Pattern"],
    },
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def jar_fingerprint(jar_path: str) -> dict:
    """jar 指纹：优先读 Maven 自带的 .sha1（零计算），否则用 size+mtime。"""
    fp = {"size": -1, "mtime_ns": -1, "sha1": ""}
    try:
        stat = os.stat(jar_path)
        fp["size"] = stat.st_size
        fp["mtime_ns"] = stat.st_mtime_ns
    except OSError:
        return fp
    sha1_file = jar_path + ".sha1"
    if os.path.isfile(sha1_file):
        try:
            with open(sha1_file, "r", encoding="utf-8", errors="replace") as f:
                fp["sha1"] = f.read().strip().split()[0][:40]
        except OSError:
            pass
    return fp


def scan_jar_classes(jar_path: str) -> dict:
    """扫描 jar，返回 {完整类名: jar路径}；跳过内部类、module/package-info。"""
    classes = {}
    try:
        with zipfile.ZipFile(jar_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".class"):
                    continue
                if name.startswith("META-INF/") or name.endswith(("module-info.class", "package-info.class")):
                    continue
                fqcn = name[:-6].replace("/", ".")
                if "$" in fqcn:  # 匿名/内部类不单独索引
                    continue
                classes[fqcn] = jar_path
    except (zipfile.BadZipFile, OSError) as exc:
        print(f"[警告] 跳过无法读取的 jar: {jar_path} ({exc})", file=sys.stderr)
    return classes


# 约定俗成的内部实现包段，任何库都过滤
INTERNAL_SEGMENTS = {"internal", "impl", "private", "shaded", "shadow"}
# 被宿主 jar 重打包(shade)进去的第三方包段；仅对 KNOWN_LIBS 已知库启用，避免误伤独立的 cglib/asm 库
SHADED_SEGMENTS = {"asm", "cglib", "objenesis", "bytebuddy", "antlr"}


def is_internal_class(fqcn: str, shaded: set = None) -> bool:
    """识别内部/重打包实现类。

    INTERNAL_SEGMENTS 始终过滤；SHADED_SEGMENTS 只在 shaded 非空（已知宿主库）时过滤，
    否则独立 cglib/asm 库（根包就叫这些名字）会被误伤。
    """
    segments = [s.lower() for s in fqcn.split(".")[:-1]]
    blocked = INTERNAL_SEGMENTS | (shaded or set())
    for seg in segments:
        if seg in blocked or seg.startswith(("internal", "private")):
            return True
    return False


def pick_key_classes(fqcn_list: list, coord_key: str) -> list:
    """为 L1 挑选关键类：内置清单优先（校验存在），再用 *Util(s)/Helper 启发式补足（过滤内部包）。"""
    known = KNOWN_LIBS.get(coord_key)
    shaded = SHADED_SEGMENTS if known else set()
    simple_index = {}
    for fqcn in fqcn_list:
        simple_index.setdefault(fqcn.rsplit(".", 1)[-1], []).append(fqcn)
    picked, seen = [], set()

    def add(fqcn):
        if fqcn and fqcn not in seen:
            seen.add(fqcn)
            picked.append(fqcn)

    def resolve_simple(simple):
        """简单名可能对应多个类（含 shade 内部类），优先返回非内部包的候选。"""
        candidates = simple_index.get(simple, [])
        public = [c for c in candidates if not is_internal_class(c, shaded)]
        return (public or candidates or [None])[0]

    if known:
        for key in known["keys"]:
            if "." in key:  # 允许写部分包名提示
                for fqcn in fqcn_list:
                    if fqcn.endswith("." + key) and len(picked) < MAX_KEY_CLASSES:
                        add(fqcn)
            else:
                resolved = resolve_simple(key)
                if resolved:
                    add(resolved)
    # 启发式补充：工具类命名，跳过内部/重打包实现类与纯常量类
    suffixes = ("Utils", "Util", "Helper", "Helpers", "Tools", "Tool", "Factory", "Builder")
    for fqcn in sorted(fqcn_list):
        if len(picked) >= MAX_KEY_CLASSES:
            break
        simple = fqcn.rsplit(".", 1)[-1]
        if not is_internal_class(fqcn, shaded) and simple.endswith(suffixes):
            add(fqcn)
    for fqcn in sorted(fqcn_list):  # 名额还有余再补 Constants 等弱信号类
        if len(picked) >= MAX_KEY_CLASSES:
            break
        simple = fqcn.rsplit(".", 1)[-1]
        if not is_internal_class(fqcn, shaded) and simple.endswith("Constants"):
            add(fqcn)
    if not picked:
        # 框架型依赖（无 Utils 命名）兜底：列包路径最浅的公共类，入口类通常在浅层
        for fqcn in sorted(fqcn_list, key=lambda x: (x.count("."), x)):
            if len(picked) >= MAX_KEY_CLASSES:
                break
            if not is_internal_class(fqcn, shaded):
                add(fqcn)
    return picked[:MAX_KEY_CLASSES]


def load_existent_map(l2_path: str) -> dict:
    if not os.path.isfile(l2_path):
        return {}
    try:
        with open(l2_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def render_l1(map_data: dict, dep_meta: dict) -> str:
    """生成给大模型读的精简能力地图 Markdown。"""
    lines = [
        "# Maven 依赖能力地图（自动生成，请勿手改）",
        "",
        f"- 生成时间：{map_data['generated_at']}",
        f"- POM：{map_data['pom_path']}",
        f"- POM 指纹：{map_data['pom_sha256'][:12]}",
        f"- 依赖数：{len(map_data['dependencies'])}，类总数：{map_data['total_classes']}",
        "- 用法：写工具方法前先在本地图定位候选类；再用 search_class_in_jars.py 确认、view_class_api.py 核签名",
        "- 依赖变更后地图会按指纹自动增量更新；本地图只列关键类，全量类清单在 dependency-map.json",
        "",
    ]
    for coord in sorted(map_data["dependencies"]):
        dep = map_data["dependencies"][coord]
        meta = dep_meta.get(coord, {})
        domains = meta.get("domains", [])
        lines.append(f"## {coord}  ({dep['scope']})")
        if domains:
            lines.append(f"- 能力域：{' / '.join(domains)}")
        else:
            lines.append("- 能力域：未内置分类，按下方类名与包名识别")
        lines.append(f"- 类数量：{dep['class_count']}")
        lines.append(f"- jar：{dep['jar']}")
        if dep["key_classes"]:
            lines.append("- 关键类：")
            for fqcn in dep["key_classes"]:
                lines.append(f"  - `{fqcn}`")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pom", default=None, help="pom.xml 路径；缺省从当前目录向上查找")
    parser.add_argument("--local-repo", default=None, help="本地 Maven 仓库；缺省自动发现")
    parser.add_argument("--map-dir", default=None, help="地图输出目录；缺省为 pom 同级 .dep-map/")
    parser.add_argument("--refresh", action="store_true", help="忽略现有缓存，全量重建")
    parser.add_argument("--transitive", action="store_true", help="含 mvn dependency:list 的传递依赖")
    args = parser.parse_args()

    try:
        pom = args.pom or me.find_pom(os.getcwd())
    except FileNotFoundError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    local_repo, repo_source = me.detect_local_repo(args.local_repo)
    root = ld.load_pom(pom)
    props = ld.resolve_properties(root)
    deps = ld.parse_dependencies(root, props)
    if args.transitive:
        deps.extend(ld.run_mvn_dependency_list(pom))

    with open(pom, "rb") as f:
        pom_hash = hashlib.sha256(f.read()).hexdigest()

    map_dir = args.map_dir or os.path.join(os.path.dirname(os.path.abspath(pom)), DEFAULT_MAP_DIRNAME)
    os.makedirs(map_dir, exist_ok=True)
    l2_path = os.path.join(map_dir, L2_NAME)
    l1_path = os.path.join(map_dir, L1_NAME)

    old = {} if args.refresh else load_existent_map(l2_path)
    # 扁平全局类索引是增量基础；依赖元数据只保留指纹/关键类，不内嵌 classes
    old_deps = old.get("dependencies", {})
    class_index = dict(old.get("class_index", {}))

    def drop_jar(index, jar):
        """从扁平索引中移除某个 jar 的全部类条目（版本升级/依赖移除时用）。"""
        if not jar:
            return
        for fqcn in list(index):
            if jar in index[fqcn]:
                index[fqcn] = [j for j in index[fqcn] if j != jar]
                if not index[fqcn]:
                    del index[fqcn]

    new_deps, dep_meta = {}, {}
    current_jars = set()
    stat_reused = stat_built = stat_missing = 0
    for d in deps:
        coord = f"{d['gid']}:{d['aid']}:{d['version'] or 'managed'}"
        coord_key = f"{d['gid']}:{d['aid']}"
        jar, exists = ld.jar_path(local_repo, d["gid"], d["aid"], d["version"], d["type"])
        if not exists:
            stat_missing += 1
            new_deps[coord] = {"scope": d["scope"], "jar": jar or "", "fingerprint": {},
                               "class_count": 0, "key_classes": []}
            dep_meta[coord] = KNOWN_LIBS.get(coord_key, {})
            continue

        current_jars.add(jar)
        fp = jar_fingerprint(jar)
        cached = old_deps.get(coord)
        if cached and cached.get("jar") == jar and cached.get("fingerprint") == fp:
            new_deps[coord] = cached  # 指纹一致，复用元数据与索引
            stat_reused += 1
        else:
            drop_jar(class_index, (cached or {}).get("jar"))  # 清旧版本残留
            classes = scan_jar_classes(jar)
            for fqcn, cls_jar in classes.items():
                class_index.setdefault(fqcn, [])
                if cls_jar not in class_index[fqcn]:
                    class_index[fqcn].append(cls_jar)
            fqcn_list = sorted(classes)
            new_deps[coord] = {
                "scope": d["scope"], "jar": jar, "fingerprint": fp,
                "class_count": len(classes),
                "key_classes": pick_key_classes(fqcn_list, coord_key),
            }
            stat_built += 1
        dep_meta[coord] = KNOWN_LIBS.get(coord_key, {})

    # 移除依赖：其 jar 不在当前集合中的条目全部清掉
    for fqcn in list(class_index):
        kept = [j for j in class_index[fqcn] if j in current_jars]
        if kept:
            class_index[fqcn] = kept
        else:
            del class_index[fqcn]

    total_classes = sum(dep["class_count"] for dep in new_deps.values())
    map_data = {
        "version": MAP_VERSION,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "pom_path": os.path.abspath(pom),
        "pom_sha256": pom_hash,
        "local_repo": local_repo,
        "repo_source": repo_source,
        "total_classes": total_classes,
        "dependencies": new_deps,
        "class_index": class_index,
    }

    with open(l2_path, "w", encoding="utf-8") as f:
        # L2 给机器读，用紧凑格式减小体积、加快加载；人读看 L1
        json.dump(map_data, f, ensure_ascii=False, separators=(",", ":"))
    with open(l1_path, "w", encoding="utf-8") as f:
        f.write(render_l1(map_data, dep_meta))

    removed = sorted(set(old_deps) - set(new_deps))
    print(f"依赖地图构建完成：{map_dir}")
    print(f"  依赖 {len(new_deps)} 个（复用缓存 {stat_reused}，新扫/更新 {stat_built}，本地缺失 {stat_missing}），类总数 {total_classes}")
    if removed:
        print(f"  移除已不在 pom 的依赖 {len(removed)} 个：{', '.join(removed[:5])}{' ...' if len(removed) > 5 else ''}")
    print(f"  L1 能力地图：{l1_path}")
    print(f"  L2 类索引  ：{l2_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
