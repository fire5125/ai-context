import sqlite3
import typer
from pathlib import Path
from ai_context.source.settings import CONTEXT_DB, AI_CONTEXT_DIR
from ai_context.source.messages import COLORS


def export_context_to_file(output_path: Path):
    """Экспортирует контекст из SQLite БД в текстовый файл в формате context.txt."""

    if not AI_CONTEXT_DIR.exists():
        typer.secho(f" - Папка .ai-context не найдена. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    if not CONTEXT_DB.exists():
        typer.secho(f" - База данных {CONTEXT_DB} не найдена. Выполните 'ai-context index'.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    output_path = Path(output_path).resolve()

    conn = sqlite3.connect(CONTEXT_DB)
    cur = conn.cursor()
    cur.execute("SELECT filepath, content FROM files ORDER BY filepath")
    rows = cur.fetchall()
    conn.close()

    if not rows:
        typer.secho(f" - База данных пуста.", fg=COLORS.WARNING)
        output_path.write_text("", encoding="utf-8")
        return

    lines = []
    for filepath, content in rows:
        lines.append(f"### FILE: {filepath} ###\n")
        lines.append(content)
        lines.append("\n" + "="*60 + "\n")

    output_path.write_text("".join(lines), encoding="utf-8")
    typer.secho(f" - Контекст экспортирован в {output_path}", fg=COLORS.SUCCESS)


def read(output_file: str = typer.Argument(default='./out_context.txt', help="Путь к выходному текстовому файлу")):
    """Команда: ai-context read ./out_context.txt — воссоздаёт в out_context.txt контекст из SQLite БД."""

    export_context_to_file(Path(output_file))