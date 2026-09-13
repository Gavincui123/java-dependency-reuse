# java-dependency-reuse

> 一个面向 AI 编程助手的 **Agent Skill**：写 Java 代码前，先盘点 Maven 依赖里**已经存在**的现成 API，强制"先查再写"，防止大模型凭记忆硬写、重复造轮子、把 API 版本记错。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

---

## 目录

- [为什么需要它](#为什么需要它)
- [它是怎么工作的](#它是怎么工作的)
- [特性](#特性)
- [目录结构](#目录结构)
- [安装](#安装)
- [快速开始](#快速开始)
- [脚本详解](#脚本详解)
- [依赖地图：一次扫描，反复复用](#依赖地图一次扫描反复复用)
- [跨平台环境自动发现](#跨平台环境自动发现)
- [内置识别的依赖](#内置识别的依赖)
- [运行要求](#运行要求)
- [限制与路线图](#限制与路线图)
- [贡献](#贡献)
- [开源协议](#开源协议)

---

## 为什么需要它

大模型写 Java 时有一个典型毛病：**不看项目 `pom.xml` 里已经引入了什么，就凭训练记忆开始手写工具方法**。于是经常出现：

- 项目里明明有 `commons-lang3`，却手写了一个边界情况没处理全的 `isBlank`；
- 凭记忆写出 `StringUtils.isEmpty`，但当前版本早已推荐 `isBlank`，甚至参数顺序都记错；
- Spring、Guava、Hutool 里一行能搞定的能力，被重新实现了一遍，还埋下 bug。

根因是模型在生成代码时，**"项目实际依赖了什么、本地 jar 里到底有哪些类和方法签名"这一信息并不在它的上下文里**。本 Skill 用一条**硬门禁流程**补上这个信息差：动手写工具方法前，必须先用脚本查清依赖里的真实 API，以**本地实际 jar** 为唯一准绳，而不是记忆。

## 它是怎么工作的

```text
准备写一个工具方法
        │
        ▼
0. 没有 .dep-map/ 就先 build_dependency_map.py 建依赖地图
        │
        ▼
1. 读 L1 能力地图 dependency-map.md ──→ 定位候选依赖 / 候选类
        │
        ▼
2. 对照速查表 common_java_libraries.md ──→ 这类需求通常用哪个类
        │
        ▼
3. search_class_in_jars.py ──→ 确认这个类确实在依赖 jar 中（走 L2 索引）
        │
        ▼
4. view_class_api.py（javap）──→ 查看本地 jar 中真实的方法签名
        │
        ▼
   依赖里有 → 必须复用，注释标注来源
   依赖里没有 → 才允许手写，并显式说明"依赖中没有，所以手写"
```

关键设计：**方法签名永远实时用 `javap` 查本地 jar，绝不靠记忆、绝不缓存过期签名**。

## 特性

- **硬门禁工作流**：SKILL.md 明确要求"写工具方法前必须走完查依赖流程"，把复用从"靠模型自觉"变成"流程强制"。
- **依赖能力地图（L1）+ 全量类索引（L2）**：扫描一次即可反复查询，不必每次重新解压扫描所有 jar。
- **内容指纹增量更新**：按 pom 指纹 + 每个 jar 的大小/修改时间/sha1 判断，没变就零扫描，单个 jar 变了只重扫它，依赖增删自动同步。
- **真实签名为准**：基于 JDK 自带的 `javap`，输出本地实际版本的公共方法，支持 `--super` 递归查看继承链。
- **跨平台、零硬编码路径**：Windows / macOS / Linux 行为一致，自动发现本地 Maven 仓库、`mvn`、`javap`，无需任何配置。
- **零第三方依赖**：所有脚本只用 Python 3 标准库，开箱即用，无需 `pip install`。
- **索引优先、实时兜底**：地图没覆盖到的新依赖会自动实时扫描，结果永远完整，不会因为地图过期而漏类。
- **内置 26 个常见依赖的能力域字典**：Commons、Guava、Hutool、Spring、Jackson、Fastjson、OkHttp 等自动归类并挑出关键类；未知依赖也有启发式兜底。

## 目录结构

```text
java-dependency-reuse/                  # ← GitHub 仓库根（项目门面）
├── README.md                           # 本文件
├── LICENSE                             # MIT 协议
├── CHANGELOG.md                        # 版本记录
├── .gitignore
└── skills/
    └── java-dependency-reuse/          # ← Skill 本体（复制到技能目录的就是这一层）
        ├── SKILL.md                    # Skill 入口：触发条件 + 硬门禁流程（AI 助手读取）
        ├── scripts/
        │   ├── maven_env.py            # 共享模块：跨平台环境发现 / settings.xml 解析 / 稳健解码
        │   ├── build_dependency_map.py # 构建 & 增量更新 L1/L2 依赖地图
        │   ├── list_dependencies.py    # 解析 pom，列依赖、定位本地 jar
        │   ├── search_class_in_jars.py # 在依赖 jar 中搜类（精确/简单名/包前缀）
        │   └── view_class_api.py       # javap 查看类的真实公共 API 签名
        └── references/
            └── common_java_libraries.md # 场景 → 现成 API 速查表（字符串/集合/判空/Bean/日期/IO/加密/JSON/HTTP…）
```

## 安装

本仓库根是项目门面，**skill 本体在 `skills/java-dependency-reuse/`**，遵循通用的 Agent Skill 目录约定（`SKILL.md` + `scripts/` + `references/`），任何按该约定加载技能的 AI 客户端都可使用。

**方式一：克隆后把 skill 本体复制到技能目录**

```bash
git clone https://github.com/<your-name>/java-dependency-reuse.git

# 把 skills/java-dependency-reuse/ 整个复制（或软链）到你的 AI 客户端的用户级 skills 目录，例如：
#   - Doubao:      <工作区>/.user_skills/java-dependency-reuse
#   - Claude Code: ~/.claude/skills/java-dependency-reuse
#   - 其他支持 SKILL.md 的客户端同理，目录名保持 java-dependency-reuse
```

**方式二：用 skills CLI 安装（结构已兼容）**

本仓库的 `skills/<name>/` 布局兼容 [skills.sh](https://skills.sh/) 生态，发布后可通过 CLI 安装：

```bash
npx skills add <your-name>/java-dependency-reuse@java-dependency-reuse
```

**方式三：作为项目内参考**

也可以直接把 `skills/java-dependency-reuse/scripts/` 拷到团队仓库，由开发者/CI 手动调用，不依赖特定 AI 客户端。

> 安装后无需任何初始化配置；脚本会在第一次运行时自动探测本机 Maven/JDK 环境。

## 快速开始

在一个含 `pom.xml` 的 Java 项目里：

```bash
# 在仓库根目录执行；脚本位于 skills/java-dependency-reuse/scripts/
# 0) 首次：构建依赖地图（生成 pom 同级的 .dep-map/，建议加入 .gitignore）
python3 skills/java-dependency-reuse/scripts/build_dependency_map.py --pom /path/to/project/pom.xml

# 1) AI 助手会先读 .dep-map/dependency-map.md（L1 能力地图）

# 2) 想找某个类在哪个依赖里（自动走 L2 索引）
python3 skills/java-dependency-reuse/scripts/search_class_in_jars.py --class StringUtils --pom /path/to/project/pom.xml

# 3) 查看该类在本地 jar 里的真实方法签名
python3 skills/java-dependency-reuse/scripts/view_class_api.py \
    --class org.apache.commons.lang3.StringUtils \
    --pom /path/to/project/pom.xml

# 实现类的方法可能在父类上，加 --super 看继承链
python3 skills/java-dependency-reuse/scripts/view_class_api.py --class org.springframework.util.StringUtils \
    --pom /path/to/project/pom.xml --super 1
```

`--pom` 缺省时会从当前目录向上查找 `pom.xml`，所以在项目目录内可直接省略。

## 脚本详解

| 脚本 | 职责 | 常用参数 |
|---|---|---|
| `maven_env.py` | 共享库（被其余脚本 import，不单独运行）：发现仓库/`mvn`/`javap`、解析 settings.xml、稳健解码 | — |
| `build_dependency_map.py` | 构建/增量更新 L1 能力地图 + L2 类索引 | `--pom` `--refresh` `--transitive` `--map-dir` `--local-repo` |
| `list_dependencies.py` | 解析 pom 列出直接依赖并定位本地 jar | `--pom` `--local-repo` `--detect-via-mvn` `--transitive` |
| `search_class_in_jars.py` | 搜类，回答"这个类在哪个依赖里" | `--class`（必填）`--pom`/`--jars` `--map-dir` `--no-map` |
| `view_class_api.py` | `javap` 查看真实公共 API | `--class`（必填，全限定名）`--pom`/`--jars` `--super N` `--no-map` |

参数说明：

- `--class`：`search` 支持完整类名、简单类名或包前缀（匹配结果分 `EXACT`/`SIMPLE`/`PREFIX`）；`view` 需要全限定名。
- `--jars`：逗号分隔的 jar 列表，与 `--pom` 二选一，用于脱离 pom 直接检查若干 jar。
- `--transitive`：默认只索引**直接依赖**（覆盖绝大多数复用场景）；加此参数会通过 `mvn dependency:list` 纳入传递依赖（需要本机有 mvn）。
- `--refresh`：忽略缓存全量重建地图。
- `--no-map`：search/view 强制不使用地图索引、改为实时扫描 jar。
- `--map-dir`：自定义地图目录，默认是 pom 同级 `.dep-map/`。
- `--local-repo`：显式指定本地 Maven 仓库，覆盖自动发现结果。

## 依赖地图：一次扫描，反复复用

为了避免"每次查类都重新解压扫描所有 jar"，同时又保证"依赖变了地图不会过时"，地图分两层：

| 层 | 文件 | 读者 | 内容 |
|---|---|---|---|
| **L1** | `.dep-map/dependency-map.md` | AI / 人 | 每个依赖 → 能力域 → 至多 20 个关键类，精简，写代码前先读 |
| **L2** | `.dep-map/dependency-map.json` | 脚本 | 全量 `全限定类名 → jar` 扁平索引，供脚本毫秒查询，不进上下文 |

**自动保鲜逻辑**

- 指纹 = pom 的 sha256 + 每个 jar 的大小/纳秒级 mtime（优先读取 Maven 自带的 `.jar.sha1`）；
- 指纹一致 → 零扫描；某个 jar 升级/更换 → 只重扫它，并先清除旧版本类残留；
- pom 新增/移除依赖 → 索引自动增删，并在输出中提示移除项；
- 地图缺失或落后时，search/view 会**自动实时扫描未覆盖的 jar 兜底**，绝不会因地图过期而漏结果；
- 方法签名刻意**不进地图、不缓存**：单类 `javap` 是毫秒级操作，实时查永远与本地版本一致。

**实测性能（macOS / SSD，JDK 17）**

| 项目规模 | 实时扫描全部 jar | 走 L2 索引 |
|---|---|---|
| 3 依赖 / 1021 类 | ~11 ms | ~7 ms |
| 9 依赖 / 4459 类 | ~35 ms | ~7 ms |
| 120 jar / 17457 类 | 550–700 ms | **11–15 ms** |

小项目两者都在毫秒级；依赖越多（典型 Spring Boot 全量依赖），索引优势越大，且全程不打开 jar，规避 Windows 实时杀毒、网络盘等慢 IO 场景。

## 跨平台环境自动发现

`maven_env.py` 不写死任何本机路径，按以下优先级探测：

- **本地仓库**：`--local-repo` → 环境变量 `MAVEN_LOCAL_REPO` → 用户级 `~/.m2/settings.xml` 的 `<localRepository>` → 全局 `${MAVEN_HOME}/conf/settings.xml` → `mvn help:evaluate`（需 `--detect-via-mvn`）→ 默认 `~/.m2/repository`（Windows 为 `%USERPROFILE%\.m2\repository`）。
- **mvn**：依次查 `PATH`、`MAVEN_HOME`、`M2_HOME`；Windows 自动识别 `mvn.cmd` 并用 `cmd /c` 包装。
- **javap**：依次查 `PATH`、`JAVA_HOME/bin`；Windows 自动识别 `javap.exe`。
- **JAVA_HOME 缺失**：macOS 走 `/usr/libexec/java_home`，Linux/Windows 从 `java` 可执行文件反推，保证未配置 JAVA_HOME 也能调起 mvn。
- **编码**：子进程输出按 UTF-8 → 系统 locale → GBK 顺序解码，兼容中文 Windows 控制台；正确处理 settings.xml 中的 `${user.home}`、`${env.X}` 变量与 Windows 反斜杠路径。

每次运行都会打印"本地仓库路径 + 仓库来源"，探测不对时用 `--local-repo` 显式覆盖即可。

## 内置识别的依赖

能力域字典覆盖 26 个高频依赖（未知依赖用命名启发式 + 浅层入口类兜底，不影响使用）：

`commons-lang3`、`commons-collections4`、`commons-codec`、`commons-io`、`guava`、`hutool-all` / `hutool-core`、`spring-core` / `spring-beans` / `spring-context` / `spring-web` / `spring-jdbc` / `spring-tx`、`jackson-core` / `jackson-databind`、`gson`、`fastjson` / `fastjson2`、`httpclient` / `httpclient5` / `okhttp`、`slf4j-api`、`lombok`、`mapstruct`、`validation-api` / `jakarta.validation-api`。

## 运行要求

- **Python 3.7+**，仅用标准库，无需安装第三方包；
- **JDK**（用到 `javap`，`JAVA_HOME` 未配置也能自动推断）；
- **Maven 可选**：解析直接依赖不需要 mvn；仅 `--transitive`（传递依赖）和 `--detect-via-mvn`（权威探测仓库）需要本机 `mvn`；
- 依赖 jar 需已存在于本地 Maven 仓库（即项目至少执行过一次 `mvn` 相关拉取）。

## 限制与路线图

当前已知边界：

- 只支持 **Maven**，暂不支持 Gradle；
- 地图以**单个 pom** 为维度，暂不支持多模块项目聚合一张地图；
- 地图是本机产物，暂不支持团队共享/集中托管；
- 只索引类级别信息，不做字节码级的方法全文索引（方法签名实时 javap 获取）。

计划中的方向：Gradle 支持、多模块聚合地图、可选的团队共享地图、更多依赖的能力域字典。欢迎在 Issues 提需求。

## 贡献

欢迎提交 Issue 和 PR：

1. Fork 本仓库并新建分支；
2. 脚本请保持**仅依赖 Python 标准库**、兼容 Windows/macOS/Linux；
3. 为新逻辑补充最小验证（可构造一个只含少量依赖的测试 pom）；
4. 提交 PR 并说明解决的场景。

## 开源协议

本项目基于 [MIT License](LICENSE) 开源，可自由使用、修改、分发，商用亦可，请保留原始版权与许可声明。
