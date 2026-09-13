#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Maven / JDK 环境自动发现（跨平台：macOS、Linux、Windows）。

三个脚本共用本模块，避免把本机路径写死。本地仓库路径按以下优先级探测：

1. 命令行 --local-repo 显式指定
2. 环境变量 MAVEN_LOCAL_REPO（非标准但常见的自定义约定）
3. 用户级 settings.xml：~/.m2/settings.xml 的 <localRepository>
4. 全局 settings.xml：${MAVEN_HOME|M2_HOME}/conf/settings.xml
5. mvn help:evaluate 实时探测（可选，需要联网解析插件，较慢）
6. 默认 ~/.m2/repository（Windows 下为 %USERPROFILE%\\.m2\\repository）

mvn 可执行文件发现：PATH → MAVEN_HOME → M2_HOME（Windows 自动识别 mvn.cmd）。
javap 可执行文件发现：PATH → JAVA_HOME（Windows 自动识别 javap.exe）。
"""
import locale
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET


# ---------------------------------------------------------------- 路径基础

def user_home() -> str:
    """跨平台用户主目录（Windows 下为 %USERPROFILE%）。"""
    return os.path.expanduser("~")


def user_m2_dir() -> str:
    """用户级 .m2 目录。"""
    return os.path.join(user_home(), ".m2")


def default_local_repo() -> str:
    """Maven 默认本地仓库。"""
    return os.path.join(user_m2_dir(), "repository")


# ---------------------------------------------------------------- 可执行文件发现

def find_maven() -> str:
    """发现 mvn 可执行文件的完整路径，找不到返回空串。"""
    for name in ("mvn", "mvn.cmd", "mvn.bat"):
        path = shutil.which(name)
        if path:
            return path
    for env_name in ("MAVEN_HOME", "M2_HOME"):
        base = os.environ.get(env_name)
        if base and os.path.isdir(base):
            for exe in ("mvn", "mvn.cmd", "mvn.bat"):
                candidate = os.path.join(base, "bin", exe)
                if os.path.isfile(candidate):
                    return candidate
    return ""


def find_javap() -> str:
    """发现 javap 可执行文件的完整路径，找不到返回空串。"""
    for name in ("javap", "javap.exe"):
        path = shutil.which(name)
        if path:
            return path
    java_home = os.environ.get("JAVA_HOME")
    if java_home and os.path.isdir(java_home):
        for exe in ("javap", "javap.exe"):
            candidate = os.path.join(java_home, "bin", exe)
            if os.path.isfile(candidate):
                return candidate
    return ""


def infer_java_home() -> str:
    """JAVA_HOME 未设置时自动推断：已有环境变量 > macOS java_home > 从 java 可执行文件反推。"""
    existing = os.environ.get("JAVA_HOME")
    if existing and os.path.isdir(existing):
        return existing
    # macOS 官方方式
    if sys.platform == "darwin" and os.path.isfile("/usr/libexec/java_home"):
        try:
            proc = subprocess.run(["/usr/libexec/java_home"], capture_output=True, timeout=10)
            out = decode_bytes(proc.stdout).strip()
            if proc.returncode == 0 and out:
                return out.splitlines()[-1].strip()
        except (subprocess.TimeoutExpired, OSError):
            pass
    # Linux / Windows：java 通常位于 <JAVA_HOME>/bin/java[.exe]
    java_exe = shutil.which("java") or shutil.which("java.exe") or ""
    if java_exe:
        real = os.path.realpath(java_exe)
        candidate = os.path.dirname(os.path.dirname(real))
        exe_name = os.path.basename(java_exe)
        if os.path.isfile(os.path.join(candidate, "bin", exe_name)):
            return candidate
    return ""


def shell_wrap(exe: str, args: list) -> list:
    """Windows 下 .cmd/.bat 不能被 CreateProcess 直接执行，需要 cmd.exe /c 包装。"""
    cmd = [exe] + list(args)
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c"] + cmd
    return cmd


def decode_bytes(data) -> str:
    """稳健解码子进程输出：依次尝试 UTF-8、系统 locale、GBK（中文 Windows），最后 replace 兜底。"""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    encodings = ["utf-8"]
    try:
        preferred = locale.getpreferredencoding(False)
        if preferred and preferred not in encodings:
            encodings.append(preferred)
    except Exception:
        pass
    for enc in ("gbk", "cp936"):
        if enc not in encodings:
            encodings.append(enc)
    for enc in encodings:
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def run_cmd(exe: str, args: list, timeout: int = None, extra_env: dict = None) -> tuple:
    """跨平台执行命令，返回 (returncode, stdout_text, stderr_text)，不抛解码异常。"""
    if not exe:
        return 127, "", "可执行文件未找到"
    env = None
    if extra_env:
        env = os.environ.copy()
        env.update(extra_env)
    proc = subprocess.run(
        shell_wrap(exe, args),
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, decode_bytes(proc.stdout), decode_bytes(proc.stderr)


# ---------------------------------------------------------------- XML 辅助（忽略命名空间）

def localname(tag: str) -> str:
    """去掉 XML 命名空间前缀，如 {http://...}project -> project。"""
    return tag.split("}", 1)[-1]


def xml_find(node, name: str):
    """按本地名查找第一个直接子节点（兼容带/不带 xmlns 的 pom、settings）。"""
    if node is None:
        return None
    for child in node:
        if localname(child.tag) == name:
            return child
    return None


def xml_findall(node, name: str) -> list:
    if node is None:
        return []
    return [child for child in node if localname(child.tag) == name]


def xml_text(node, name: str) -> str:
    child = xml_find(node, name)
    if child is not None and child.text:
        return child.text.strip()
    return ""


# ---------------------------------------------------------------- settings.xml / 本地仓库

def expand_maven_props(value: str) -> str:
    """展开 settings.xml 中可能出现的 ${user.home}、${env.X}、${maven.home} 等变量。"""
    if not value:
        return value
    value = value.strip()

    def repl(match):
        key = match.group(1)
        if key == "user.home":
            return user_home()
        if key.startswith("env."):
            return os.environ.get(key[4:], match.group(0))
        if key in ("maven.home", "maven.conf"):
            return os.environ.get("MAVEN_HOME") or os.environ.get("M2_HOME") or match.group(0)
        return os.environ.get(key, match.group(0))

    # 必须用函数式 replacement：字符串模板会把 Windows 路径中的反斜杠当转义（如 \r 被解释为回车）
    value = re.sub(r"\$\{([^}]+)\}", repl, value)
    return os.path.expanduser(os.path.expandvars(value))


def candidate_settings_files() -> list:
    """按 Maven 生效顺序返回存在的 settings.xml 路径：用户级优先，全局其次。"""
    candidates = [os.path.join(user_m2_dir(), "settings.xml")]
    for env_name in ("MAVEN_HOME", "M2_HOME"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(os.path.join(base, "conf", "settings.xml"))
    mvn = find_maven()
    if mvn:
        # mvn 位于 <maven_home>/bin/mvn，全局 settings 在同级 conf/
        maven_home = os.path.dirname(os.path.dirname(mvn))
        candidates.append(os.path.join(maven_home, "conf", "settings.xml"))
    seen, ordered = set(), []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in seen and os.path.isfile(path):
            seen.add(norm)
            ordered.append(norm)
    return ordered


def read_local_repo_from_settings() -> tuple:
    """从 settings.xml 读取 <localRepository>，返回 (绝对路径, 来源文件)；读不到返回 (None, None)。"""
    for settings_path in candidate_settings_files():
        try:
            root = ET.parse(settings_path).getroot()
            node = xml_find(root, "localRepository")
            if node is not None and node.text and node.text.strip():
                repo = os.path.abspath(expand_maven_props(node.text))
                return repo, settings_path
        except (ET.ParseError, OSError):
            continue
    return None, None


def ask_mvn_local_repo(timeout: int = 90) -> str:
    """通过 mvn help:evaluate 获取权威本地仓库路径（可能触发插件下载，较慢）。"""
    mvn = find_maven()
    if not mvn:
        return ""
    extra_env = {}
    if not os.environ.get("JAVA_HOME"):
        inferred = infer_java_home()
        if inferred:
            extra_env["JAVA_HOME"] = inferred
    try:
        code, out, err = run_cmd(
            mvn,
            ["-q", "help:evaluate", "-Dexpression=settings.localRepository", "-DforceStdout"],
            timeout=timeout,
            extra_env=extra_env or None,
        )
    except subprocess.TimeoutExpired:
        print("[提示] mvn help:evaluate 超时，回退到其他探测方式。", file=sys.stderr)
        return ""
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    if code != 0 or not lines:
        err_lines = [l for l in err.strip().splitlines() if l.strip()]
        detail = err_lines[-1] if err_lines else f"exit={code}"
        print(f"[提示] mvn help:evaluate 未取得仓库路径（{detail}），回退到其他探测方式。", file=sys.stderr)
        return ""
    return lines[-1]


def detect_local_repo(explicit: str = None, via_mvn: bool = False) -> tuple:
    """按优先级探测本地 Maven 仓库，返回 (repo_path, 来源说明)。

    explicit: 命令行 --local-repo；via_mvn: 是否允许调用 mvn 实时探测（兜底）。
    """
    if explicit:
        return os.path.abspath(expand_maven_props(explicit)), "命令行参数 --local-repo"

    env_repo = os.environ.get("MAVEN_LOCAL_REPO")
    if env_repo and env_repo.strip():
        return os.path.abspath(expand_maven_props(env_repo)), "环境变量 MAVEN_LOCAL_REPO"

    repo, source = read_local_repo_from_settings()
    if repo:
        return repo, f"settings.xml：{source}"

    if via_mvn:
        repo = ask_mvn_local_repo()
        if repo:
            return os.path.abspath(repo), "mvn help:evaluate 实时探测"

    return default_local_repo(), "Maven 默认位置 ~/.m2/repository"


# ---------------------------------------------------------------- pom 发现

def find_pom(start: str) -> str:
    """从 start 目录向上递归查找 pom.xml，到文件系统根仍找不到则抛 FileNotFoundError。"""
    current = os.path.abspath(start)
    while True:
        candidate = os.path.join(current, "pom.xml")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            raise FileNotFoundError(f"未找到 pom.xml（从 {start} 向上查找已到根目录）")
        current = parent
