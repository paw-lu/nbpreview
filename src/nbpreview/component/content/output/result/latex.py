"""Render LaTeX equations."""
from pylatexenc import latex2text


def render_latex(markup: str) -> str:
    """Render latex as unicode characters."""
    rendered_latex: str = latex2text.LatexNodes2Text(
        math_mode="text", fill_text=True, strict_latex_spaces=False
    ).latex_to_text(markup)
    return rendered_latex
