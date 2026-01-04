import sys
import os
import time
import sqlite3
import typer
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from ai_context.source.settings import (
    AI_CONTEXT_DIR,
    CONTEXT_DB,
    CONTEXT_FILE,
    STOP_FLAG_FILE,
)
from ai_context.source.messages import COLORS
from .index import load_ai_ignore, should_index

# Внутренний флаг — чтобы отличать внутренний запуск
_INTERNAL_FLAG = "--_run-watchdog"


class ContextUpdater(FileSystemEventHandler):
    """
    Обработчик изменений файловой системы для автоматического обновления контекста проекта.

    Следит за событиями создания, изменения и удаления файлов в рабочей директории.
    При изменении файла:
      - проверяет, должен ли он входить в контекст (по правилам .ai-ignore, размеру, бинарности),
      - обновляет или удаляет запись в SQLite-базе context.db,
      - повторно генерирует текстовый файл context.txt для совместимости с отладочными инструментами.

    Игнорирует все изменения внутри папки .ai-context/, чтобы избежать рекурсивных событий.
    """

    def __init__(self):
        self.ai_ignore = load_ai_ignore()
        typer.secho(" - Наблюдение за изменениями запущено...", fg=COLORS.INFO)

    def on_any_event(self, event) -> None:
        """
        Обрабатывает все файловые события (создание, изменение, удаление) в рабочей директории.

        Метод:
          - игнорирует события внутри папки `.ai-context/`,
          - определяет относительный путь файла относительно корня проекта,
          - при удалении — удаляет запись из SQLite-базы,
          - при создании/изменении — проверяет, должен ли файл входить в контекст
            (по `.ai-ignore`, размеру, бинарности),
            → если да — обновляет запись в БД,
            → если нет — удаляет его из контекста (на случай, если он был ранее добавлен),
          - после любого изменения перезаписывает `context.txt` для совместимости с отладочными инструментами.

        Поддерживаемые типы событий: 'created', 'modified', 'deleted'.
        """
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

        # Игнорируем всё внутри .ai-context/
        if rel_path_str.startswith(".ai-context" + os.sep) or rel_path_str == ".ai-context":
            return

        # Выводим файл, который изменился
        typer.secho(f" - Событие: {event.event_type} → {rel_path}", fg=COLORS.DEBUG)

        conn = sqlite3.connect(CONTEXT_DB)
        cur = conn.cursor()

        if event.event_type == "deleted":
            cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
            typer.secho(f" - Удалён из контекста: {rel_path}", fg=COLORS.WARNING)
        else:
            if should_index(src_path, self.ai_ignore):
                try:
                    content = src_path.read_text(encoding="utf-8", errors="replace")
                    cur.execute(
                        "INSERT OR REPLACE INTO files (filepath, content) VALUES (?, ?)",
                        (rel_path_str, content),
                    )
                    typer.secho(f" - Обновлён в контексте: {rel_path}", fg=COLORS.SUCCESS)
                except Exception as e:
                    typer.secho(f" - Ошибка чтения {rel_path}: {e}", fg=COLORS.WARNING)
            else:
                cur.execute("DELETE FROM files WHERE filepath = ?", (rel_path_str,))
                typer.secho(f" - Исключён из контекста: {rel_path}", fg=COLORS.INFO)

        conn.commit()
        conn.close()
        self.export_context_to_file()

    def export_context_to_file(self):
        """
        Экспортирует текущий контекст из SQLite-базы в текстовый файл context.txt.

        Собирает содержимое всех проиндексированных файлов из таблицы `files`,
        объединяет их в единый документ с разделителями вида:
            === file: <путь> ===
            <содержимое>
        и записывает результат в `.ai-context/context.txt`.

        Используется для отладки, внешних инструментов или резервного просмотра контекста.
        """

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
    """Запускает наблюдатель в отдельном терминале."""

    if not AI_CONTEXT_DIR.exists():
        typer.secho(" - Папка .ai-context не найдена. Выполните 'ai-context init'.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    if not CONTEXT_DB.exists():
        typer.secho(" - База данных не найдена. Выполните 'ai-context index'.", fg=COLORS.ERROR)
        raise typer.Exit(1)

    # Сохраняем PID
    pid = str(os.getpid())
    STOP_FLAG_FILE.write_text(pid, encoding="utf-8")
    typer.secho(f" - PID процесса сохранён: {pid}", fg=COLORS.INFO)

    event_handler = ContextUpdater()
    observer = Observer()
    observer.schedule(event_handler, Path.cwd(), recursive=True)
    observer.start()

    typer.secho(" - Режим наблюдения активен. Закройте окно для остановки.", fg=COLORS.SUCCESS)

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        typer.secho("\n - Получен сигнал завершения...", fg=COLORS.INFO)

    finally:
        observer.stop()
        observer.join()
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def stop_daemon():
    """Останавливает демон."""
    if not STOP_FLAG_FILE.exists():
        typer.secho(" - Демон не запущен.", fg=COLORS.INFO)
        return

    try:
        pid = int(STOP_FLAG_FILE.read_text(encoding="utf-8").strip())
        if os.name == "nt":
            os.system(f"taskkill /F /PID {pid} >nul 2>&1")
        else:
            os.kill(pid, 9)
        STOP_FLAG_FILE.unlink()
        typer.secho(" - Демон остановлен.", fg=COLORS.SUCCESS)

    except Exception as e:
        typer.secho(f" - Не удалось остановить демон: {e}", fg=COLORS.ERROR)
        if STOP_FLAG_FILE.exists():
            STOP_FLAG_FILE.unlink()


def watchdog(
        stop: bool = typer.Option(False, "--stop", "-s", help="Остановить демон"),
):
    """Команда: ai-context watchdog [--stop]"""
    if stop:
        stop_daemon()
        return

    # Уже внутри наблюдателя — запускаем логику
    if _INTERNAL_FLAG in sys.argv:
        start_observer()
        return

    # Запускаем в новом окне терминала
    cmd = [sys.executable, "-m", "ai_context.cli", "watchdog", _INTERNAL_FLAG]

    try:
        if os.name == "nt":
            # Windows: открываем новое окно cmd, которое НЕ закрывается (/k)
            subprocess.Popen(
                ["cmd", "/k"] + cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                close_fds=False
            )
        else:
            # Unix: можно использовать xterm, gnome-terminal, или просто фон
            # Для простоты — запускаем в фоне, но оставляем вывод
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=None,  # чтобы видеть вывод
                stderr=None,
            )
        typer.secho(" - Watchdog запущен в новом окне терминала.", fg=typer.colors.GREEN)

    except Exception as e:
        typer.secho(f" - Не удалось запустить watchdog: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)
