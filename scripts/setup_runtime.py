"""Create isolated optional runtimes for Plot and external API modes."""

from __future__ import annotations

import argparse
import os
import subprocess
import venv
from pathlib import Path

from paperbanana_common import get_codex_home


RUNTIME_IMPORTS = {
    "plot": ["matplotlib", "numpy", "pandas", "seaborn"],
    "api": [
        "google.genai",
        "httpx",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "seaborn",
        "yaml",
    ],
}


def runtime_root(mode: str, codex_home: str | Path | None = None) -> Path:
    """
    获取指定可选模式的虚拟环境目录。
    Args:
        input: mode 为 plot 或 api，codex_home 为可选 Codex 用户目录。

    Returns:
        Output：虚拟环境绝对路径。
    """
    if mode not in RUNTIME_IMPORTS:
        raise ValueError("mode 必须是 plot 或 api")
    home = (
        Path(codex_home).expanduser().resolve() if codex_home else get_codex_home()
    )
    return home / "paperbanana" / "venvs" / mode


def runtime_python_path(mode: str, codex_home: str | Path | None = None) -> Path:
    """
    获取指定可选模式的 Python 解释器路径。
    Args:
        input: mode 为 plot 或 api，codex_home 为可选 Codex 用户目录。

    Returns:
        Output：平台对应的虚拟环境 Python 路径。
    """
    root = runtime_root(mode, codex_home)
    return root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def runtime_is_ready(mode: str, codex_home: str | Path | None = None) -> bool:
    """
    检查虚拟环境及所需模块是否可用。
    Args:
        input: mode 为 plot 或 api，codex_home 为可选 Codex 用户目录。

    Returns:
        Output：全部依赖可导入时为 True。
    """
    python_path = runtime_python_path(mode, codex_home)
    if not python_path.is_file():
        return False
    imports = ";".join(f"import {name}" for name in RUNTIME_IMPORTS[mode])
    result = subprocess.run(
        [str(python_path), "-I", "-c", imports],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def install_runtime(mode: str, codex_home: str | Path | None = None) -> Path:
    """
    创建隔离虚拟环境并安装所选模式依赖。
    Args:
        input: mode 为 plot 或 api，codex_home 为可选 Codex 用户目录。

    Returns:
        Output：安装完成的虚拟环境 Python 路径。
    """
    root = runtime_root(mode, codex_home)
    root.parent.mkdir(parents=True, exist_ok=True)
    if not runtime_python_path(mode, codex_home).is_file():
        venv.EnvBuilder(with_pip=True).create(root)
    python_path = runtime_python_path(mode, codex_home)
    requirements = (
        Path(__file__).resolve().parents[1] / f"requirements-{mode}.txt"
    )
    subprocess.run(
        [
            str(python_path),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "-r",
            str(requirements),
        ],
        check=True,
    )
    if not runtime_is_ready(mode, codex_home):
        raise RuntimeError(f"{mode} 运行环境安装后仍无法导入所需依赖")
    return python_path


def main() -> int:
    """
    检查或安装隔离运行环境。
    Args:
        input: mode 以及 --check 或 --install。

    Returns:
        Output：检查成功或安装成功时返回 0。
    """
    parser = argparse.ArgumentParser(description="Manage PaperBanana optional runtimes")
    parser.add_argument("--mode", choices=["plot", "api"], required=True)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if args.check:
        python_path = runtime_python_path(args.mode)
        if runtime_is_ready(args.mode):
            print(python_path)
            return 0
        print(f"{args.mode} runtime is not ready: {python_path}")
        return 1
    print(install_runtime(args.mode))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
