"""Command-line interface."""
import click


@click.command()
@click.version_option()
def main() -> None:
    """nbpreview."""


if __name__ == "__main__":
    main(prog_name="nbpreview")  # pragma: no cover
