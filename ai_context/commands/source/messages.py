from typer import colors


class COLORS:
    SUCCESS = colors.GREEN
    INFO = colors.WHITE
    DEBUG = colors.BRIGHT_BLUE
    WARNING = colors.YELLOW
    ERROR = colors.BRIGHT_RED


INIT_FINISH_ALL_COMMANDS = [
    " > Используй следующие команды:",
    " >>> 'ai-context edit-prompt' для редактирования промпта",
    " >>> 'ai-context index' для сканирования проекта и добавления его в контекст",
    " >>> 'ai-context read ./path/to/output_file.txt' для записи контекста в файл",
    " >>> 'ai-context watchdog' для включения отслеживания изменений в проекте",
    " >>> 'ai-context chat' для общения с AI (в процессе разработки)",
]

