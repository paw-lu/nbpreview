"""Sphinx configuration."""
from datetime import datetime

project = "nbpreview"
author = "Paulo S. Costa"
copyright = f"{datetime.now().year}, {author}"
extensions = [
    "myst_parser",
    "sphinx_click",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinx-favicon",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",  # Must be loaded after sphinx.ext.napoleon
    "sphinxext.opengraph",
]
intersphinx_mapping = {
    "click": ("https://click.palletsprojects.com/en/8.0.x/", None),
    "pylatexenc": ("https://pylatexenc.readthedocs.io/en/latest/", None),
    "python": ("https://docs.python.org/3", None),
    "lxml": ("https://lxml.de/apidoc/", None),
    "rich": ("https://rich.readthedocs.io/en/latest/", None),
}
autodoc_typehints = "description"
myst_heading_anchors = 3
html_theme = "furo"
pygments_style = "material"
pygments_dark_style = "material"
html_theme_options = {
    "light_logo": "images/logo_light.svg",
    "dark_logo": "images/logo_dark.svg",
    "sidebar_hide_name": True,
    "light_css_variables": {
        "color-problematic": "#21005D",
        "color-foreground-primary": "#1C1B1F",
        "color-background-primary": "#FFFBFE",
        "color-background-secondary": "#FFFBFE",
        "color-background-hover": "#EADDFF",
        "color-background-hover--transparent": "#EADDFF",
        "color-background-border": "#E7E0EC",
        "color-announcement-background": "#EADDFF",
        "color-announcement-text": "#21005D",
        "color-brand-primary": "#6750A4",
        "color-brand-content": "#6750A4",
        "color-highlighted-background": "#E8DEF8",
        "color-guilabel-background": "#EADDFF",
        "color-guilabel-border": "#6750A4",
        "color-card-background": "#E7E0EC",
        "color-admonition-title": "#21005D",
        "color-admonition-title-background": "#EADDFF",
        "color-admonition-title--important": "#21005D",
        "color-admonition-title-background--important": "#EADDFF",
        "color-admonition-title--note": "#21005D",
        "color-admonition-title-background--note": "#EADDFF",
        "color-admonition-title--seealso": "#21005D",
        "color-admonition-title-background--seealso": "#EADDFF",
        "color-admonition-title--attention": "#410E0B",
        "color-admonition-title-background--attention": "#F9DEDC",
        "color-admonition-title--danger": "#410E0B",
        "color-admonition-title-background--danger": "#F9DEDC",
        "color-admonition-title--error": "#410E0B",
        "color-admonition-title-background--error": "#F9DEDC",
        "color-admonition-title--caution": "#31111D",
        "color-admonition-title-background--caution": "#FFD8E4",
        "color-admonition-title--warning": "#31111D",
        "color-admonition-title-background--warning": "#FFD8E4",
        "color-admonition-title--tip": "#1D192B",
        "color-admonition-title-background--tip": "#E8DEF8",
        "color-admonition-title--hint": "#1D192B",
        "color-admonition-title-background--hint": "#E8DEF8",
        "toc-font-size": "1rem",
        "sidebar-item-font-size": "1rem",
        "toc-title-font-size": "1.25rem",
        "font-stack": "Roboto, -apple-system, BlinkMacSystemFont,"
        " Segoe UI, Helvetica, Arial, sans-serif, Apple Color Emoji,"
        " Segoe UI Emoji;",
        "font-stack--monospace": "Fira Code, monospace;",
    },
    "dark_css_variables": {
        "color-problematic": "#EADDFF",
        "color-foreground-primary": "#E6E1E5",
        "color-background-primary": "#1C1B1F",
        "color-background-secondary": "#1C1B1F",
        "color-background-hover": "#4F378B",
        "color-background-hover--transparent": "#4F378B",
        "color-background-border": "#49454F",
        "color-announcement-background": "#4F378B",
        "color-announcement-text": "#EADDFF",
        "color-brand-primary": "#D0BCFF",
        "color-brand-content": "#D0BCFF",
        "color-highlighted-background": "#4A4458",
        "color-guilabel-background": "#4F378B",
        "color-guilabel-border": "#D0BCFF",
        "color-card-background": "#49454F",
        "color-admonition-title": "#EADDFF",
        "color-admonition-title-background": "#4F378B",
        "color-admonition-title--important": "#EADDFF",
        "color-admonition-title-background--important": "#4F378B",
        "color-admonition-title--note": "#EADDFF",
        "color-admonition-title-background--note": "#4F378B",
        "color-admonition-title--seealso": "#EADDFF",
        "color-admonition-title-background--seealso": "#4F378B",
        "color-admonition-title--attention": "#F9DEDC",
        "color-admonition-title-background--attention": "#8C1D18",
        "color-admonition-title--danger": "#F9DEDC",
        "color-admonition-title-background--danger": "#8C1D18",
        "color-admonition-title--error": "#F9DEDC",
        "color-admonition-title-background--error": "#8C1D18",
        "color-admonition-title--caution": "#FFD8E4",
        "color-admonition-title-background--caution": "#633B48",
        "color-admonition-title--warning": "#FFD8E4",
        "color-admonition-title-background--warning": "#633B48",
        "color-admonition-title--tip": "#E8DEF8",
        "color-admonition-title-background--tip": "#4A4458",
        "color-admonition-title--hint": "#E8DEF8",
        "color-admonition-title-background--hint": "#4A4458",
    },
}
html_static_path = ["_static"]
html_css_files = ["css/custom.css"]
favicons = [
    {
        "rel": "apple-touch-icon",
        "sizes": "180x180",
        "static-file": "images/favicon/apple-touch-icon.png",
    },
    {
        "rel": "icon",
        "type": "image/png",
        "sizes": "32x32",
        "static-file": "images/favicon/favicon-32x32.png",
    },
    {
        "rel": "icon",
        "type": "image/png",
        "sizes": "16x16",
        "static-file": "images/favicon/favicon-16x16.png",
    },
    {
        "rel": "manifest",
        "static-file": "images/favicon/site.webmanifest",
    },
    {
        "rel": "mask-icon",
        "static-file": "images/favicon/safari-pinned-tab.svg",
        "color": "#6750a4",
    },
    {
        "rel": "shortcut icon",
        "static-file": "images/favicon/favicon.ico",
    },
    {
        "rel": "icon",
        "type": "image/svg+xml",
        "static-file": "images/favicon/favicon.svg",
    },
]
ogp_site_url = "https://nbpreview.readthedocs.io/"
ogp_site_name = "nbpreview"
ogp_image = "https://nbpreview.readthedocs.io/en/latest/_images/logo_light.svg"
