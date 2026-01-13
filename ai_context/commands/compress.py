import ast
import typer
import sqlite3
from pathlib import Path
from typing import List, Tuple
from loguru import logger

from ai_context.source.settings import CONTEXT_DB, AI_CONTEXT_DIR


def extract_python_signatures(content: str) -> List[str]:
    """Извлекает сигнатуры классов, функций и методов из Python-файла."""

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return ["[Ошибка синтаксиса Python — файл пропущен]"]
    signatures = []

    def _get_docstring(node):
        if ast.get_docstring(node):
            doc = ast.get_docstring(node).strip()
            return doc.split("\n")[0].rstrip(".")
        return None

    def _format_args(args) -> str:
        parts = []
        all_args = args.posonlyargs + args.args + args.kwonlyargs
        for a in all_args:
            if a.annotation:
                parts.append(f"{a.arg}: {ast.unparse(a.annotation)}")
            else:
                parts.append(a.arg)
        if args.vararg:
            parts.append(f"*{args.vararg.arg}")
        if args.kwarg:
            parts.append(f"**{args.kwarg.arg}")
        return ", ".join(parts)

    def _visit(node, prefix=""):
        if isinstance(node, ast.ClassDef):
            sig = f"class {node.name}"
            doc = _get_docstring(node)
            signatures.append(f"{sig}  →  {doc or 'нет описания'}")
            for item in node.body:
                _visit(item, prefix=f"{node.name}.")
        elif isinstance(node, ast.FunctionDef):
            args_str = _format_args(node.args)
            return_annot = f" → {ast.unparse(node.returns)}" if node.returns else ""
            sig = f"def {prefix}{node.name}({args_str}){return_annot}"
            doc = _get_docstring(node)
            signatures.append(f"{sig}  →  {doc or 'нет описания'}")
        elif isinstance(node, ast.AsyncFunctionDef):
            args_str = _format_args(node.args)
            return_annot = f" → {ast.unparse(node.returns)}" if node.returns else ""
            sig = f"async def {prefix}{node.name}({args_str}){return_annot}"
            doc = _get_docstring(node)
            signatures.append(f"{sig}  →  {doc or 'нет описания'}")

    for node in tree.body:
        _visit(node)

    return signatures if signatures else ["[Нет классов или функций на верхнем уровне]"]


def generate_file_summary(filepath: str, content: str) -> str:
    """Генерирует резюме файла."""

    path = Path(filepath)
    total_lines = len(content.splitlines())
    if path.suffix == ".py":
        sigs = extract_python_signatures(content)
        summary = "\n".join(f"  • {s}" for s in sigs[:20])
    else:
        summary = "  → Язык не поддерживается для сигнатур. Используется первый непустой фрагмент."
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        if lines:
            summary += f"\n• {lines[0][:100]}..."
    return f"Файл: {filepath} | {total_lines} строк\n{summary}\n"


def extract_summaries_from_db() -> List[str]:
    """Читает все проиндексированные файлы и генерирует резюме (только для index.py)."""

    if not CONTEXT_DB.exists():
        logger.error(" - База данных контекста не найдена. Выполните 'ai-context index'.")
        raise typer.Exit(1)
    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("SELECT filepath, content FROM files ORDER BY filepath")
    rows: List[Tuple[str, str]] = cur.fetchall()
    conn.close()
    summaries = []
    for filepath, content in rows:
        try:
            summary = generate_file_summary(filepath, content)
            summaries.append(summary.strip())
        except Exception as e:
            summaries.append(f"Файл: {filepath} | ОШИБКА при анализе: {e}")
    return summaries


def load_summary_from_db() -> str:
    """Загружает резюме из кэша project_summary."""

    if not CONTEXT_DB.exists():
        logger.error(" - База данных не найдена. Выполните 'ai-context index'.")
        raise typer.Exit(1)
    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("SELECT summary_text FROM project_summary WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        logger.warning(" - Резюме не найдено в БД. Выполните 'ai-context index'.")
        raise typer.Exit(1)
    return row[0]


def compress(output_path: Path = Path("out_resume.txt")):
    """
    Команда: ai-context compress [--output ./out_resume.txt] Экспортирует **уже сгенерированное** резюме проекта из БД в файл.
    """

    if not AI_CONTEXT_DIR.exists():
        logger.error(" - Папка .ai-context не найдена. Выполните 'ai-context init'.")
        raise typer.Exit(1)

    summary_text = load_summary_from_db()
    output_path.write_text(summary_text, encoding="utf-8")
    logger.success(f" - Резюме экспортировано в {output_path.absolute()}")