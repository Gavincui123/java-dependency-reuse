# Changelog

本项目的版本变更记录，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-09-13

首个公开版本。

### Added

- **硬门禁工作流**：SKILL.md 规定写工具方法前必须按"建地图 → 读 L1 → 对照速查表 → search 确认 → javap 核签名"的顺序执行，依赖里有现成 API 必须复用，没有才允许手写并说明。
- **`build_dependency_map.py`**：一次扫描生成两层依赖地图：
  - L1 `dependency-map.md`：依赖 → 能力域 → 关键类，供 AI/人阅读；
  - L2 `dependency-map.json`：全量 `全限定类名 → jar` 扁平索引，供脚本毫秒查询。
  - 基于 pom sha256 + jar 大小/修改时间/sha1 的内容指纹增量更新：未变零扫描、单 jar 变更只重扫它、依赖增删自动同步、`--refresh` 全量重建。
  - 内置 26 个高频依赖（Commons/Guava/Hutool/Spring/Jackson/Fastjson/OkHttp 等）的能力域字典与关键类挑选；未知依赖用工具类命名启发式 + 浅层入口类兜底；自动过滤 internal/impl 及被 shade 进宿主 jar 的重打包类。
- **`list_dependencies.py`**：解析 pom.xml 列出直接依赖并定位本地 jar，支持 `--transitive`（mvn dependency:list）与 `--detect-via-mvn`。
- **`search_class_in_jars.py`**：精确/简单名/包前缀三种匹配；优先走 L2 索引，未覆盖依赖自动实时扫描兜底，支持 `--no-map`、`--jars`。
- **`view_class_api.py`**：基于 JDK 自带 `javap` 输出本地实际 jar 的真实公共方法签名，支持 `--super N` 递归继承链；签名实时获取、不缓存。
- **`maven_env.py`**：Windows/macOS/Linux 统一的 Maven 仓库、`mvn`、`javap` 自动发现；解析用户级/全局 settings.xml 与变量；JAVA_HOME 缺失时自动推断；UTF-8/locale/GBK 稳健解码。
- **`references/common_java_libraries.md`**：按"想实现的功能"组织的现成 API 速查表，覆盖字符串、集合、判空、Bean 拷贝、日期、IO、加密摘要、HTTP、JSON 等场景及常见陷阱。

### 特性说明

- 全部脚本仅使用 Python 3 标准库，无需 pip 安装，要求 Python 3.7+。
- 实测：120 jar / 17457 类规模下，L2 索引查询约 11–15 ms，实时扫描约 550–700 ms。
