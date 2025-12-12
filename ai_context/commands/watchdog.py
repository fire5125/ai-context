import sys
import os
import time
import sqlite3
import typer
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    CONTEXT_FILE,
    STOP_FLAG_FILE,
)
from .source.messages import ICONS, COLORS
from .index import load_ai_ignore, should_index

# 🔑 Внутренний флаг — пользователь его НЕ видит
_INTERNAL_DAEMON_FLAG = "--no-daemon"


class ContextUpdater(FileSystemEventHandler):
    def __init__(self):
        self.ai_ignore = load_ai_ignore()
        typer.secho(f" - {ICONS.info} Наблюдение за изменениями запущено...", fg=COLORS.INFO)

    def on_any_event(self, event):
        if event.is_directory:
            return
        if event.event_type not in ("created", "modified", "deleted"):
            return

        src_path = Path(event.src_path).resolve()
        try:
            rel_path = src_path.relative_to(Path.cwd())
            rel_path_str = str(rel_path)
        except ValueError:
            return

        # 🔥 Игнорируем ВСЁ внутри .ai-context/
        if rel_path_str.startswith(".ai-context" + os.sep) or rel_path_str == ".ai-context":
            return

        typer.secho(f" - {ICONS.file} Событие: {event.event_type} → {rel_path}", fg=COLORS.DEBUG)

        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()

        if event.event_type == "deleted":
            cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
            typer.secho(f" - {ICONS.warning} Удалён из контекста: {rel_path}", fg=COLORS.WARNING)
        else:
            if should_index(src_path, self.ai_ignore):
                try:
                    content = src_path.read_text(encoding="utf-8", errors="replace")
                    cur.execute("INSERT OR REPLACE INTO files (filepath, content) VALUES (?, ?)", (rel_path_str, content))
                    typer.secho(f" - {ICONS.success} Обновлён в контексте: {rel_path}", fg=COLORS.SUCCESS)
                except Exception as e:
                    typer.secho(f" - {ICONS.error} Ошибка чтения {rel_path}: {e}", fg=COLORS.WARNING)
            else:
                cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
                typer.secho(f" - {ICONS.info} Исключён из контекста: {rel_path}", fg=COLORS.INFO)

        conn.commit()
        conn.close()
        self.export_context_to_file()

    def export_context_to_file(self):
        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()
        cur.execute("SELECT filepath, content FROM files ORDER BY filepath")
        rows = cur.fetchall()
        conn.close()

        lines = []
        for filepath, content in rows:
            lines.append(f"### FILE: {filepath} ###\n")
            lines.append(content)
            lines.append("\n" + "=" * 60 + "\n")

        CONTEXT_FILE.write_text("".join(lines), encoding="utf-8")


def start_observer():
    """Основной цикл наблюдателя — создаёт PID-файл."""
    if not AI_CONTEXT_DIR.exists():
        typer.secho(f" - {ICONS.error} Папка .ai-context не найдена. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)
    if not CONTEXT_DB.exists():
        typer.secho(f" - {ICONS.error} База данных не найдена. Выполните 'ai-context index'.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    # ✅ Создаём PID-файл
    pid = str(os.getpid())
    STOP_FLAG_FILE.write_text(pid, encoding="utf-8")
    typer.secho(f" - {ICONS.info} PID процесса сохранён в {STOP_FLAG_FILE} ({pid})", fg=COLORS.INFO)

    event_handler = ContextUpdater()
    observer = Observer()
    observer.schedule(event_handler, Path.cwd(), recursive=True)
    observer.start()

    typer.secho(f" - {ICONS.ai} Режим наблюдения активен.", fg=COLORS.SUCCESS)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        typer.secho(f"\n - {ICONS.info} Получен сигнал завершения...", fg=COLORS.INFO)
    finally:
        observer.stop()
        observer.join()
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def stop_daemon():
    if not STOP_FLAG_FILE.exists():
        typer.secho(" - ℹ️  Демон не запущен.", fg=COLORS.INFO)
        return

    try:
        pid = int(STOP_FLAG_FILE.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            os.system(f"taskkill /F /PID {pid} >nul 2>&1")
        else:
            os.kill(pid, 9)
        STOP_FLAG_FILE.unlink()
        typer.secho(" - ✅ Демон остановлен.", fg=COLORS.SUCCESS)
    except Exception as e:
        typer.secho(f" - ❌ Не удалось остановить демон: {e}", fg=COLORS.ERROR)
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def watchdog(
        daemon: bool = typer.Option(False, "--daemon", "-d", help="Запустить в фоне (демон)"),
        stop: bool = typer.Option(False, "--stop", "-s", help="Остановить запущенный демон"),
):
    if stop:
        stop_daemon()
        return

    if daemon:
        # 💡 Это внешний вызов: запускаем subprocess с внутренним флагом
        cmd = [sys.executable, "-m", "ai_context.cli", "watchdog", _INTERNAL_DAEMON_FLAG]
        try:
            if os.name == "nt":
                subprocess.Popen(
                    cmd,
                    creationflags=subprocess.DETACHED_PROCESS,
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                subprocess.Popen(
                    cmd,
                    start_new_session=True,
                    close_fds=True,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            typer.secho(" - ✅ Watchdog запущен в фоне.", fg=typer.colors.GREEN)
        except Exception as e:
            typer.secho(f" - ❌ Не удалось запустить демон: {e}", fg=typer.colors.RED)
            raise typer.Exit(1)
    else:
        # Интерактивный режим ИЛИ внутренний вызов демона
        if _INTERNAL_DAEMON_FLAG in sys.argv:
            # Это фоновый процесс → запускаем наблюдатель с PID-файлом
            start_observer()
        else:
            # Обычный пользовательский запуск (блокирующий)
            typer.secho(" - ℹ️  Запуск в интерактивном режиме...", fg=typer.colors.WHITE)
            start_observer()