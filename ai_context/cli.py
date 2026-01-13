import typer
from .commands import init, prompt, index, read_context, ai_watchdog, chat, compress


app = typer.Typer(
    name="ai-context",
    help="CLI tool to provide AI with context from your codebase",
    no_args_is_help=True,
    rich_markup_mode="rich",
    context_settings={"allow_extra_args": True},
)

app.command()(init.init)
app.command()(prompt.edit_prompt)
app.command()(index.index)
app.command()(read_context.read)
app.command()(ai_watchdog.watchdog)
app.command()(chat.chat)
app.command()(compress.compress)


if __name__ == "__main__":
    app()