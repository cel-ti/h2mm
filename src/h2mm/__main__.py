import click
from tabulate import tabulate
from h2mm.mgr import H2MM
from h2mm.model import H2MMCfg
from h2mm.utils import wrap_text

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if not H2MMCfg.exists():
        click.echo("H2MM is not initialized. Initializing...")
        try:
            from tkinter import Tk
            from tkinter.filedialog import askdirectory
            root = Tk()
            root.withdraw()
            game_path = askdirectory(title="Select the game directory")
            if not game_path:
                raise Exception("No game directory selected")
        except Exception:  
            game_path = click.prompt("Enter the path to the game directory", type=str)
        H2MMCfg.create(game_path)
    ctx.obj = H2MM.load()
    ctx.ensure_object(H2MM)

@cli.group(name="list")
def list_group():
    pass

@list_group.command()
@click.pass_context
def installed(ctx):
    h2mm : H2MM = ctx.obj
    table = h2mm.list_installed_mods()
    # Clean up the data and wrap long text
    if isinstance(table, list) and table and isinstance(table[0], dict):
        cleaned_table = []
        for row in table:
            cleaned_row = {}
            # Remove hash and clean up each value
            for key, value in row.items():
                if key != 'hash':
                    if key == 'installed_file':
                        text = wrap_text(value, 25)
                    elif key == 'name':
                        text = wrap_text(value, 35)  # Reduced width for CJK
                    else:  # description
                        text = wrap_text(value, 15)
                    cleaned_row[key] = text
            cleaned_table.append(cleaned_row)
        table = cleaned_table
    
    click.echo(tabulate(
        table,
        headers="keys",
        tablefmt="simple",
        numalign="left",
        stralign="left",
        disable_numparse=True
    ))

if __name__ == "__main__":

    cli()
