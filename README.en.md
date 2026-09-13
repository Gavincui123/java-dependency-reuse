# java-dependency-reuse

> [中文](README.md) | **English**
>
> An **Agent Skill** for AI coding assistants: before writing Java code, take stock of the **APIs already available in your Maven dependencies** and enforce "look it up first", so the model stops writing from memory, reinventing the wheel, and misremembering API versions.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.7%2B-blue.svg)]()
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)]()

---

## Table of Contents

- [Why you need this](#why-you-need-this)
- [How it works](#how-it-works)
- [Features](#features)
- [Repository structure](#repository-structure)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Scripts](#scripts)
- [Dependency map: scan once, query many times](#dependency-map-scan-once-query-many-times)
- [Cross-platform auto-detection](#cross-platform-auto-detection)
- [Built-in library recognition](#built-in-library-recognition)
- [Requirements](#requirements)
- [Limitations & roadmap](#limitations--roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Why you need this

Large language models writing Java have a familiar bad habit: **they never look at what the project's `pom.xml` actually pulls in and just start writing utility code from training memory.** Typical symptoms:

- `commons-lang3` is already on the classpath, yet the model hand-rolls an `isBlank` that mishandles edge cases;
- It writes `StringUtils.isEmpty` from memory, but the pinned version recommends `isBlank` instead, or gets the argument order wrong;
- A one-liner from Spring / Guava / Hutool gets reimplemented from scratch — and bugs ship with it.

The root cause: when generating code, the model has **no access to "what dependencies this project really has and what classes/signatures actually live in the local jars."** This Skill closes that information gap with a **hard gate** — before writing a utility method, it must query the real APIs from the **local jars** and treat the script output as the source of truth, not memory.

## How it works

```text
About to write a utility method
        │
        ▼
0. No .dep-map/? Run build_dependency_map.py to build one
        │
        ▼
1. Read L1 dependency-map.md ──────→ locate candidate dependency / candidate class
        │
        ▼
2. Check common_java_libraries.md ─→ which library usually covers this need
        │
        ▼
3. search_class_in_jars.py ────────→ confirm the class exists in dependency jars (via L2 index)
        │
        ▼
4. view_class_api.py (javap) ──────→ read the real method signatures in the local jar
        │
        ▼
   Exists in deps → must reuse, annotate the source in a comment
   Not present    → hand-write is allowed, but say so explicitly: "no existing X in deps"
```

Key design: **method signatures are always fetched live with `javap` from the local jar — never memorized, never cached.**

## Features

- **Hard-gate workflow**: SKILL.md mandates the lookup sequence before any utility method; reuse is enforced by process, not model goodwill.
- **L1 capability map + L2 full class index**: scan once, query many times, no repeated jar decompression.
- **Content-fingerprint incremental updates**: pom hash + per-jar size/mtime/sha1 decide what changed; unchanged → zero scans, one jar changed → rescan only it, added/removed deps → index synced automatically.
- **Real signatures as source of truth**: based on JDK's built-in `javap`, outputs the public API of the actually-installed version; `--super` walks the inheritance chain.
- **Cross-platform, zero hard-coded paths**: Windows / macOS / Linux behave identically; auto-detects the local Maven repo, `mvn`, and `javap`.
- **Zero third-party dependencies**: pure Python 3 standard library, works out of the box.
- **Index-first, live fallback**: newly added deps not covered by the map are scanned live automatically, so results are never stale or incomplete.
- **26 built-in capability profiles**: Commons, Guava, Hutool, Spring, Jackson, Fastjson, OkHttp… are auto-categorized with hand-picked key classes; unknown libraries get a heuristic fallback.

## Repository structure

```text
java-dependency-reuse/                  # ← repo root (project landing page)
├── README.md                           # Chinese README
├── README.en.md                        # This file (English)
├── LICENSE                             # MIT
├── CHANGELOG.md
├── .gitignore
└── skills/
    └── java-dependency-reuse/          # ← the Skill itself (copy this layer into your skills dir)
        ├── SKILL.md                    # Skill entry: triggers + hard-gate workflow (read by the AI)
        ├── scripts/
        │   ├── maven_env.py            # Shared: cross-platform env discovery / settings.xml / decoding
        │   ├── build_dependency_map.py # Build & incrementally update the L1/L2 map
        │   ├── list_dependencies.py    # Parse pom, list deps, locate local jars
        │   ├── search_class_in_jars.py # Search classes in dependency jars
        │   └── view_class_api.py       # javap: real public API signatures
        └── references/
            └── common_java_libraries.md # Task → ready-made API cheat sheet
```

## Installation

The repo root is the project landing page; **the Skill itself lives in `skills/java-dependency-reuse/`**, following the generic Agent Skill layout (`SKILL.md` + `scripts/` + `references/`).

**Option 1: clone and copy the Skill folder into your skills directory**

```bash
git clone https://github.com/Gavincui123/java-dependency-reuse.git

# Copy (or symlink) skills/java-dependency-reuse/ into your AI client's user skills dir, e.g.:
#   - Doubao:      <workspace>/.user_skills/java-dependency-reuse
#   - Claude Code: ~/.claude/skills/java-dependency-reuse
#   - any other SKILL.md-compatible client, keep the folder name as java-dependency-reuse
```

**Option 2: via the skills CLI (layout is already compatible)**

This repo's `skills/<name>/` layout works with the [skills.sh](https://skills.sh/) ecosystem:

```bash
npx skills add Gavincui123/java-dependency-reuse@java-dependency-reuse
```

**Option 3: as a standalone reference**

You can also copy `skills/java-dependency-reuse/scripts/` into your monorepo for developers / CI to call directly, with no AI client required.

> No setup needed after install; scripts auto-detect your local Maven/JDK on first run.

## Quick start

Inside a Java project that has a `pom.xml` (run from the repo root):

```bash
# 0) First time: build the dependency map (writes .dep-map/ next to the pom; add it to .gitignore)
python3 skills/java-dependency-reuse/scripts/build_dependency_map.py --pom /path/to/project/pom.xml

# 1) The AI reads .dep-map/dependency-map.md (the L1 capability map)

# 2) Find which dependency provides a class (uses the L2 index automatically)
python3 skills/java-dependency-reuse/scripts/search_class_in_jars.py --class StringUtils --pom /path/to/project/pom.xml

# 3) Inspect the real method signatures in the local jar
python3 skills/java-dependency-reuse/scripts/view_class_api.py \
    --class org.apache.commons.lang3.StringUtils \
    --pom /path/to/project/pom.xml

# Methods may live on a parent class; use --super to walk the chain
python3 skills/java-dependency-reuse/scripts/view_class_api.py --class org.springframework.util.StringUtils \
    --pom /path/to/project/pom.xml --super 1
```

When run inside the project directory, `--pom` can be omitted (it walks upward to find `pom.xml`).

## Scripts

| Script | Purpose | Common flags |
|---|---|---|
| `maven_env.py` | Shared library (imported, not run directly): env discovery, settings.xml parsing, robust decoding | — |
| `build_dependency_map.py` | Build / incrementally update the L1 map + L2 index | `--pom` `--refresh` `--transitive` `--map-dir` `--local-repo` |
| `list_dependencies.py` | Parse pom, list direct deps, locate local jars | `--pom` `--local-repo` `--detect-via-mvn` `--transitive` |
| `search_class_in_jars.py` | Find which dependency provides a class | `--class` (required) `--pom`/`--jars` `--map-dir` `--no-map` |
| `view_class_api.py` | `javap` real public API of a class | `--class` (required, FQCN) `--pom`/`--jars` `--super N` `--no-map` |

Notes:

- `--class` for `search` accepts an FQCN, a simple class name, or a package prefix (results tagged `EXACT` / `SIMPLE` / `PREFIX`); `view` needs an FQCN.
- `--jars`: comma-separated jar list, mutually exclusive with `--pom`, for inspecting arbitrary jars.
- `--transitive`: only **direct dependencies** are indexed by default; pass it to include transitive deps via `mvn dependency:list` (requires local mvn).
- `--refresh`: rebuild the map from scratch, ignoring cache.
- `--no-map`: force live jar scanning, bypassing the L2 index.
- `--map-dir`: custom map directory; defaults to `.dep-map/` next to the pom.
- `--local-repo`: override the auto-detected local Maven repository.

## Dependency map: scan once, query many times

To avoid rescanning every jar on every query **and** to keep the map fresh when deps change, it is split in two layers:

| Layer | File | Read by | Contents |
|---|---|---|---|
| **L1** | `.dep-map/dependency-map.md` | AI / human | per dependency → capability domain → up to 20 key classes; read before writing code |
| **L2** | `.dep-map/dependency-map.json` | scripts | flat `FQCN → jar` index for millisecond lookups; never loaded into context |

**Auto-refresh logic**

- Fingerprint = pom sha256 + per-jar size / nanosecond mtime (Maven's own `.jar.sha1` is preferred when available);
- Fingerprint unchanged → zero scans; a single jar upgraded/replaced → rescan only it and drop the old version's classes;
- Deps added/removed in pom → index entries added/removed, with a notice printed;
- If the map is missing or stale, search/view **automatically scans the uncovered jars live as a fallback**, so results are always complete;
- Method signatures are deliberately **not stored** in the map: `javap` on a single class is milliseconds, so querying live always matches the local version.

**Measured performance (macOS / SSD, JDK 17)**

| Project size | Live scan all jars | Via L2 index |
|---|---|---|
| 3 deps / 1021 classes | ~11 ms | ~7 ms |
| 9 deps / 4459 classes | ~35 ms | ~7 ms |
| 120 jars / 17457 classes | 550–700 ms | **11–15 ms** |

Small projects are milliseconds either way; the larger the dependency set (a typical full Spring Boot dependency tree), the bigger the win — and the index never opens jar files, avoiding Windows real-time antivirus and slow network-disk IO.

## Cross-platform auto-detection

`maven_env.py` hard-codes no local paths and probes in this priority order:

- **Local repo**: `--local-repo` → `MAVEN_LOCAL_REPO` env → user `~/.m2/settings.xml` `<localRepository>` → global `${MAVEN_HOME}/conf/settings.xml` → `mvn help:evaluate` (only with `--detect-via-mvn`) → default `~/.m2/repository` (`%USERPROFILE%\.m2\repository` on Windows).
- **mvn**: `PATH`, then `MAVEN_HOME`, then `M2_HOME`; on Windows `mvn.cmd` is detected and wrapped with `cmd /c`.
- **javap**: `PATH`, then `JAVA_HOME/bin`; `javap.exe` detected on Windows.
- **No JAVA_HOME**: macOS uses `/usr/libexec/java_home`; Linux/Windows infer it from the `java` executable, so mvn still launches on machines without JAVA_HOME configured.
- **Encoding**: subprocess output is decoded as UTF-8 → system locale → GBK, covering Chinese Windows consoles; `${user.home}` / `${env.X}` variables and Windows backslash paths are handled correctly.

Every run prints "local repo path + how it was detected"; override with `--local-repo` if needed.

## Built-in library recognition

Capability profiles cover 26 high-frequency libraries (unknown libs still work via name heuristics + shallow entry-class fallback):

`commons-lang3`, `commons-collections4`, `commons-codec`, `commons-io`, `guava`, `hutool-all` / `hutool-core`, `spring-core` / `spring-beans` / `spring-context` / `spring-web` / `spring-jdbc` / `spring-tx`, `jackson-core` / `jackson-databind`, `gson`, `fastjson` / `fastjson2`, `httpclient` / `httpclient5` / `okhttp`, `slf4j-api`, `lombok`, `mapstruct`, `validation-api` / `jakarta.validation-api`.

## Requirements

- **Python 3.7+**, standard library only, no pip install;
- **JDK** (uses `javap`; works even without `JAVA_HOME` set);
- **Maven optional**: parsing direct deps does not need mvn; only `--transitive` and `--detect-via-mvn` require a local `mvn`;
- dependency jars must exist in the local Maven repo (the project has been resolved by maven at least once).

## Limitations & roadmap

Current boundaries:

- Maven only, no Gradle yet;
- one map per pom, no multi-module aggregation yet;
- map is machine-local, no team-wide sharing yet;
- class-level indexing only — method bodies are not indexed (signatures come live from javap).

Planned: Gradle support, multi-module aggregated map, optional shared team map, more library profiles. Open an Issue for requests.

## Contributing

Issues and PRs welcome:

1. Fork and create a branch;
2. Keep scripts **Python standard-library only** and compatible with Windows/macOS/Linux;
3. Add a minimal repro (a small test pom with a few deps) for new behavior;
4. Open a PR describing the use case.

## License

Distributed under the [MIT License](LICENSE). Free to use, modify, and distribute, including commercially, provided the original copyright and license notice are retained.
