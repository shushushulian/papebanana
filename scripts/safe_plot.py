"""Validate and render model-generated Matplotlib code in an isolated process."""

from __future__ import annotations

import argparse
import ast
import builtins
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ALLOWED_IMPORT_ROOTS = {
    "math",
    "matplotlib",
    "numpy",
    "pandas",
    "seaborn",
    "statistics",
}
BLOCKED_CALL_NAMES = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}
BLOCKED_ATTRIBUTES = {
    "dump",
    "dumps",
    "fromfile",
    "genfromtxt",
    "imread",
    "imsave",
    "load",
    "loads",
    "loadtxt",
    "os",
    "read_clipboard",
    "read_csv",
    "read_excel",
    "read_feather",
    "read_json",
    "read_parquet",
    "read_pickle",
    "save",
    "savefig",
    "savetxt",
    "savez",
    "savez_compressed",
    "socket",
    "subprocess",
    "sys",
    "to_clipboard",
    "to_csv",
    "to_excel",
    "to_feather",
    "to_json",
    "to_parquet",
    "to_pickle",
    "tofile",
}


class PlotSecurityError(ValueError):
    """Raised when generated plot code violates the execution policy."""


class PlotCodeValidator(ast.NodeVisitor):
    """Reject unsafe imports, calls, and attribute access."""

    def visit_Import(self, node: ast.Import) -> None:
        """
        校验普通 import 语句。
        Args:
            input: Python AST Import 节点。

        Returns:
            Output：无，非法导入时抛出异常。
        """
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root not in ALLOWED_IMPORT_ROOTS:
                raise PlotSecurityError(f"禁止导入模块：{alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """
        校验 from import 语句。
        Args:
            input: Python AST ImportFrom 节点。

        Returns:
            Output：无，非法导入时抛出异常。
        """
        root = (node.module or "").split(".", 1)[0]
        if node.level or root not in ALLOWED_IMPORT_ROOTS:
            raise PlotSecurityError(f"禁止导入模块：{node.module or 'relative import'}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """
        禁止访问私有或危险名称。
        Args:
            input: Python AST Name 节点。

        Returns:
            Output：无，非法名称时抛出异常。
        """
        if node.id.startswith("_"):
            raise PlotSecurityError(f"禁止访问私有名称：{node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """
        禁止文件、网络、进程和私有属性访问。
        Args:
            input: Python AST Attribute 节点。

        Returns:
            Output：无，非法属性时抛出异常。
        """
        if node.attr.startswith("_") or node.attr in BLOCKED_ATTRIBUTES:
            raise PlotSecurityError(f"禁止访问属性：{node.attr}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """
        禁止动态执行和系统相关函数调用。
        Args:
            input: Python AST Call 节点。

        Returns:
            Output：无，非法调用时抛出异常。
        """
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_CALL_NAMES:
            raise PlotSecurityError(f"禁止调用函数：{node.func.id}")
        if isinstance(node.func, ast.Attribute) and node.func.attr in BLOCKED_ATTRIBUTES:
            raise PlotSecurityError(f"禁止调用方法：{node.func.attr}")
        self.generic_visit(node)


def validate_plot_code(code: str) -> ast.Module:
    """
    解析并校验生成的 Plot Python 代码。
    Args:
        input: 待执行的 Python 源代码。

    Returns:
        Output：通过校验的 AST 模块。
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as error:
        raise PlotSecurityError(f"Plot 代码语法错误：{error}") from error
    PlotCodeValidator().visit(tree)
    return tree


def _safe_builtins() -> dict:
    """
    构造 Plot 执行所需的最小内置函数集合。
    Args:
        input: 无。

    Returns:
        Output：受限 builtins 字典。
    """
    allowed_names = {
        "Exception",
        "ValueError",
        "__import__",
        "abs",
        "all",
        "any",
        "bool",
        "dict",
        "enumerate",
        "float",
        "int",
        "len",
        "list",
        "map",
        "max",
        "min",
        "print",
        "range",
        "round",
        "set",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    }
    return {name: getattr(builtins, name) for name in allowed_names}


def _render_worker(code_path: Path, output_path: Path, dpi: int) -> None:
    """
    在隔离进程中执行已校验代码并保存 PNG。
    Args:
        input: code_path 为代码文件，output_path 为图片路径，dpi 为分辨率。

    Returns:
        Output：无，失败时抛出异常。
    """
    code = code_path.read_text(encoding="utf-8")
    tree = validate_plot_code(code)
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    plt.close("all")
    plt.rcdefaults()
    execution_globals = {
        "__builtins__": _safe_builtins(),
        "__name__": "__paperbanana_plot__",
    }
    exec(compile(tree, str(code_path), "exec"), execution_globals)
    if not plt.get_fignums():
        raise RuntimeError("Plot 代码没有创建 Matplotlib Figure")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, format="png", bbox_inches="tight", dpi=dpi)
    plt.close("all")


def _isolated_environment(temp_root: Path) -> dict[str, str]:
    """
    构造不携带用户敏感变量的子进程环境。
    Args:
        input: temp_root 为临时工作目录。

    Returns:
        Output：最小化环境变量字典。
    """
    keep = {
        "CONDA_PREFIX",
        "LD_LIBRARY_PATH",
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
    }
    environment = {key: value for key, value in os.environ.items() if key in keep}
    environment.update(
        {
            "HOME": str(temp_root),
            "MPLCONFIGDIR": str(temp_root / "mpl"),
            "PYTHONNOUSERSITE": "1",
            "TEMP": str(temp_root),
            "TMP": str(temp_root),
        }
    )
    return environment


def render_plot(
    code: str,
    output_path: str | Path,
    code_output_path: str | Path | None = None,
    dpi: int = 300,
    timeout: int = 60,
) -> Path:
    """
    校验 Plot 代码并在隔离子进程中渲染。
    Args:
        input: code 为源代码，output_path 为 PNG，code_output_path 为代码副本。

    Returns:
        Output：成功生成的 PNG 绝对路径。
    """
    validate_plot_code(code)
    output = Path(output_path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with tempfile.TemporaryDirectory(prefix="paperbanana-plot-") as temp_name:
        temp_root = Path(temp_name)
        temporary_code = temp_root / "plot.py"
        temporary_code.write_text(code, encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            str(Path(__file__).resolve()),
            "--worker",
            "--code",
            str(temporary_code),
            "--output",
            str(output),
            "--dpi",
            str(dpi),
        ]
        try:
            result = subprocess.run(
                command,
                cwd=temp_root,
                env=_isolated_environment(temp_root),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Plot 渲染超过 {timeout} 秒") from error
        if result.returncode != 0 or not output.is_file():
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(f"Plot 渲染失败：{detail}")

    if code_output_path:
        code_output = Path(code_output_path).expanduser().resolve()
        code_output.parent.mkdir(parents=True, exist_ok=True)
        code_output.write_text(code, encoding="utf-8")
    return output


def main() -> int:
    """
    提供安全 Plot 渲染和内部 worker 命令行入口。
    Args:
        input: code、output、dpi、timeout 和 worker 参数。

    Returns:
        Output：进程退出码，成功为 0。
    """
    parser = argparse.ArgumentParser(description="Safely render Matplotlib code")
    parser.add_argument("--code", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--code-output", default="")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    code_path = Path(args.code).expanduser().resolve()
    if args.worker:
        _render_worker(code_path, Path(args.output).expanduser().resolve(), args.dpi)
        return 0
    render_plot(
        code_path.read_text(encoding="utf-8"),
        args.output,
        args.code_output or None,
        dpi=args.dpi,
        timeout=args.timeout,
    )
    print(Path(args.output).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

