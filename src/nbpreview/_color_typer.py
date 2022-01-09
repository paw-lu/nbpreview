"""Typer intergraged with click-help-colors."""
from typing import Any, Callable, Dict, Optional, Type

import click_help_colors
import typer
from click import Command
from typer.models import CommandFunctionType


class TyperHelpColorsCommand(click_help_colors.HelpColorsCommand):  # type: ignore[misc]
    """Hard coded command help colors for all Typer commands."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Constructor."""
        super().__init__(*args, **kwargs)
        self.help_headers_color = "magenta"
        self.help_options_color = "cyan"


class ColorTyper(typer.Typer):
    """Typer with a colorized help."""

    def command(
        self,
        name: Optional[str] = None,
        *,
        cls: Optional[Type[Command]] = TyperHelpColorsCommand,
        context_settings: Optional[Dict[Any, Any]] = None,
        help: Optional[str] = None,
        epilog: Optional[str] = None,
        short_help: Optional[str] = None,
        options_metavar: str = "[OPTIONS]",
        add_help_option: bool = True,
        no_args_is_help: bool = False,
        hidden: bool = False,
        deprecated: bool = False,
    ) -> Callable[[CommandFunctionType], CommandFunctionType]:
        """Add help colors to the Typer command."""
        return super().command(
            name=name,
            cls=cls,
            context_settings=context_settings,
            help=help,
            epilog=epilog,
            short_help=short_help,
            options_metavar=options_metavar,
            add_help_option=add_help_option,
            no_args_is_help=no_args_is_help,
            hidden=hidden,
            deprecated=deprecated,
        )
