---
name: java-dependency-reuse
description: 写 Java 代码前先盘点 Maven 依赖中已有的现成 API，避免重复造轮子、防止凭记忆硬写代码；跨平台（Windows/macOS/Linux），自动发现 Maven 本地仓库、mvn 与 javap，无需写死路径；一次扫描生成"依赖能力地图"并按内容指纹增量更新，后续查询直接走索引。适用于：(1) 开发或修改 Java 后端代码，需要字符串/集合处理、判空断言、Bean 拷贝、日期、IO 文件、加密摘要、JSON、HTTP 等常见工具功能时；(2) 准备手写工具类或静态方法之前，先确认 pom.xml 依赖及本地 Maven 仓库中是否已有对应实现（Apache Commons、Guava、Hutool、Spring 等）；(3) 用户提出"用依赖里已有的功能""别自己写""不要重复造轮子""先查依赖"等要求时。
---

# Java 依赖复用（Maven）

写 Java 代码时优先复用 Maven 依赖中已有的 API，不凭记忆硬写，不重复造轮子。

## 依赖地图：一次扫描，反复复用

每个项目首次使用时构建一张依赖地图，放在 **pom.xml 同级的 `.dep-map/` 目录**：

- **L1 `dependency-map.md`（给模型读）**：每个依赖 → 能力域 → 关键类清单，精简，写代码前先 Read 它，快速判断"这个需求该用哪个依赖的哪个类"。
- **L2 `dependency-map.json`（给脚本查）**：全量 `全限定类名 → jar` 扁平索引，search/view 自动加载，**不要把它读进上下文**（可能很大），由脚本 grep 级查询。

```bash
python3 <skill>/scripts/build_dependency_map.py --pom <项目/pom.xml>
```

地图按 **pom 内容指纹 + 每个 jar 的 size/mtime/sha1 指纹** 自动保鲜：指纹一致零扫描，个别 jar 变了只重扫它，依赖增删自动增删索引；怀疑不准时加 `--refresh` 全量重建。建议把 `.dep-map/` 加进项目 `.gitignore`（本机产物，不入库）。

## 硬门禁：写工具方法前必须走完 5 步

**写任何工具方法/静态方法之前**，按顺序执行：

0. **确保地图存在**：项目没有 `.dep-map/` 就先运行 `build_dependency_map.py`（有则跳过，增量更新是自动的）
1. **读 L1 能力地图**：Read `<项目>/.dep-map/dependency-map.md`，定位候选依赖与候选类
2. **对照速查表**：判断需求属于哪类常见功能，Read `references/common_java_libraries.md` 对应章节（字符串/集合/判空/Bean 拷贝/日期/IO/加密/JSON/HTTP…）
3. **确认存在**：在依赖 jar 中搜索候选类（自动优先走 L2 索引，未覆盖的依赖实时扫描兜底，结果永远完整）
   ```bash
   python3 <skill>/scripts/search_class_in_jars.py --class StringUtils --pom <项目/pom.xml>
   ```
4. **核对真实签名**：用 javap 查看该类在**本地实际 jar** 中的真实方法签名（不靠记忆；签名不缓存，每次实时，最准）
   ```bash
   python3 <skill>/scripts/view_class_api.py --class org.apache.commons.lang3.StringUtils --pom <项目/pom.xml>
   ```
   实现类需要父类方法时加 `--super 1` 查看继承链。

**门禁判定**：
- 依赖中存在满足需求的类/方法 → **必须复用**，代码旁注释标注来源（如 `// 复用 commons-lang3 StringUtils.isBlank`）
- 不存在 → 允许手写，但在回复中说明"依赖中没有现成的 X，所以手写"，让用户可复核

## 触发时的行为约束

- 不要直接开始写代码。先问自己：这个功能是"常见工具能力"还是"业务逻辑"？前者先过门禁，后者直接写。
- 不要凭记忆写 Commons/Guava/Hutool/Spring 的 API：`view_class_api.py` 的输出才是准绳（依赖版本不同，API 可能有差异）。
- 报错优先怀疑"API 写错/依赖里没有这个类"，用脚本核实后再改代码，而不是先加新依赖。
- 若确认项目依赖中确实缺失某能力，且新增依赖合理（与现有依赖风格一致、无冲突风险），可提议新增；否则手写并说明。

## 环境自动发现（跨平台，无需配置路径）

脚本不写死任何本机路径，在 Windows / macOS / Linux 上行为一致，由 `scripts/maven_env.py` 统一探测：

- **本地 Maven 仓库**按优先级自动发现：`--local-repo` 显式指定 → 环境变量 `MAVEN_LOCAL_REPO` → 用户级 `~/.m2/settings.xml` 的 `<localRepository>` → 全局 `${MAVEN_HOME}/conf/settings.xml` → `mvn help:evaluate`（仅加 `--detect-via-mvn` 时）→ 默认 `~/.m2/repository`（Windows 为 `%USERPROFILE%\.m2\repository`）。
- **mvn**：依次查 PATH、`MAVEN_HOME`、`M2_HOME`；Windows 自动识别 `mvn.cmd` 并用 `cmd /c` 包装。
- **javap**：依次查 PATH、`JAVA_HOME/bin`；Windows 自动识别 `javap.exe`。
- **JAVA_HOME 缺失时自动推断**：macOS 走 `/usr/libexec/java_home`，Linux/Windows 从 `java` 可执行文件反推，保证 mvn 在未配置 JAVA_HOME 的电脑上也能被脚本调起。
- **编码**：子进程输出按 UTF-8 → 系统 locale → GBK 顺序解码，兼容中文 Windows 控制台。
- 每次运行 `list_dependencies.py`/`build_dependency_map.py` 都会打印"本地仓库路径 + 仓库来源"，路径不对时先看这两行；仍不对就用 `--local-repo` 显式覆盖。
- 脚本只用 Python 3 标准库，无需 pip 安装任何依赖。

## 脚本

| 脚本 | 作用 | 常用参数 |
|---|---|---|
| `maven_env.py` | 共享模块：跨平台发现仓库/mvn/javap、解析 settings.xml、稳健解码（被其余脚本 import，不单独运行） | — |
| `build_dependency_map.py` | 构建/增量更新 L1 能力地图 + L2 类索引到 `.dep-map/` | `--pom`、`--refresh`（全量重建）、`--transitive`（含传递依赖）、`--map-dir`、`--local-repo` |
| `list_dependencies.py` | 解析 pom.xml 列出依赖 + 定位本地 jar | `--pom`（缺省自动向上找）、`--local-repo`、`--detect-via-mvn`、`--transitive` |
| `search_class_in_jars.py` | 在依赖 jar 中搜类（精确/简单名/包前缀）；优先走 L2 索引，未覆盖部分实时扫描兜底 | `--class`、`--pom` / `--jars`、`--map-dir`、`--no-map`（强制实时）、`--local-repo` |
| `view_class_api.py` | javap 查看类真实公共 API 签名；先查 L2 定位 jar 再实时 javap | `--class`、`--pom` / `--jars`、`--super N`、`--map-dir`、`--no-map` |

默认只索引 pom 的**直接依赖**（绝大多数复用场景够用）；需要传递依赖时给 build/search/view 加 `--transitive`（底层走 `mvn dependency:list`）。方法签名不进地图、不缓存：单类 javap 是毫秒级，实时查永远与本地 jar 版本一致。

## 参考文档

- `references/common_java_libraries.md`：**核心速查表**。写工具方法前必须查。按"想实现的功能"组织，覆盖字符串/集合/判空/Bean 拷贝/日期/IO/加密/JSON/HTTP 及常见陷阱。

## 例外（允许不复用）

- 性能敏感路径（如热点循环）且库 API 有明显开销
- 库 API 语义与需求不符（如判空规则、空值处理差异）
- 项目约束禁止新增该依赖（甲方指定、轻量项目）
- 用户明确要求手写

以上情况手写时，在代码注释中记录不复用原因。
