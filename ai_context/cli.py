import typer
from commands import init, prompt, index,read_context, watchdog


app = typer.Typer(
    name="ai-context",
    help="CLI tool to provide AI with context from your codebase",
    no_args_is_help=True,
    rich_markup_mode="rich"
)

app.command()(init.init)
app.command()(prompt.edit_prompt)
app.command()(index.index)
app.command()(read_context.read_context)
app.command()(watchdog.watchdog)


if __name__ == "__main__":
    app()