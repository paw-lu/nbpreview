<!-- title-start -->

![nbpreview light logo](https://github.com/paw-lu/nbpreview/blob/main/docs/_static/images/logo_light.svg?raw=True#gh-light-mode-only)
![nbpreview dark logo](docs/_static/images/logo_dark.svg#gh-dark-mode-only)

# nbpreview

<!-- title-end -->

[![PyPI](https://img.shields.io/pypi/v/nbpreview.svg)](https://pypi.org/project/nbpreview/)
[![Status](https://img.shields.io/pypi/status/nbpreview.svg)](https://pypi.org/project/nbpreview/)
[![Python Version](https://img.shields.io/pypi/pyversions/nbpreview)](https://pypi.org/project/nbpreview)
[![License](https://img.shields.io/pypi/l/nbpreview)](https://opensource.org/licenses/MIT)
[![Read the documentation at https://nbpreview.readthedocs.io/](https://img.shields.io/readthedocs/nbpreview/latest.svg?label=Read%20the%20Docs)](https://nbpreview.readthedocs.io/)
[![Tests](https://github.com/paw-lu/nbpreview/workflows/Tests/badge.svg)](https://github.com/paw-lu/nbpreview/actions?workflow=Tests)
[![Codecov](https://codecov.io/gh/paw-lu/nbpreview/branch/main/graph/badge.svg)](https://codecov.io/gh/paw-lu/nbpreview)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![tryceratops](https://img.shields.io/badge/try%2Fexcept%20style-tryceratops%20%F0%9F%A6%96%E2%9C%A8-black)](https://github.com/guilatrova/tryceratops)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

A terminal viewer for Jupyter notebooks.

## Features

<!-- github-only -->

## Requirements

- Python 3.8+

## Installation

<!-- installation-start -->

nbpreview can be installed through [pipx] or [pip] from [PyPI](https://pypi.org/).

[pipx] provides an easy way to install Python applications in isolated environments.
[See the documentation for how to install pipx.](https://pypa.github.io/pipx/installation/#install-pipx)

```console
% pipx install nbpreview
```

If [pipx] is not installed,
nbpreview may also be installed via [pip]:

```console
% python -m pip install nbpreview
```

[pipx]: https://pypa.github.io/pipx/
[pip]: https://pip.pypa.io/

<!-- installation-end -->

## Usage

To use nbpreview,
simply type `nbpreview` into your terminal followed by the path of the notebook you wish to view.

```console
% nbpreview notebook.ipynb
```

See the [command-line reference](https://nbpreview.readthedocs.io/en/latest/usage.html) for details on options.

## Contributing

Contributions are very welcome.
To learn more, see the [contributor guide](https://github.com/paw-lu/nbpreview/blob/main/CONTRIBUTING.md).

## License

Distributed under the terms of the [MIT license](https://opensource.org/licenses/MIT),
_nbpreview_ is free and open source software.

## Issues

If you encounter any problems,
please [file an issue](https://github.com/paw-lu/nbpreview/issues) along with a detailed description.

## Prior art

### Similar tools

<!-- similar-tools-start -->

Thanks to [@joouha](https://github.com/joouha) for [maintaining list of these tools](https://euporie.readthedocs.io/en/latest/pages/related.html#notebook-viewers).
Many of the projects here were found directly on their page.

- [ipynb-term](https://github.com/PaulEcoffet/ipynbviewer)
- [ipynbat](https://github.com/edgarogh/ipynbat)
- [ipynbviewer](https://github.com/edgarogh/ipynbat)
- [jcat](https://github.com/ktw361/jcat)
- [jupview](https://github.com/Artiomio/jupview)
- [jupytui](https://github.com/mosiman/jupytui)
- [jut](https://github.com/kracekumar/jut)
- [nbcat](https://github.com/jlumpe/nbcat)
- [nbtui](https://github.com/chentau/nbtui)
- [nbv](https://github.com/lepisma/nbv)
- [Read-Jupyter-Notebook](https://github.com/qcw171717/Read-Jupyter-Notebook)

<!-- similar-tools-end -->

### Complimentary tools

<!-- complimentary-tools-start -->

If you're interested in complimentary tools
that help improve the terminal experience for notebooks,
there are many amazing projects out there.

- **[bat](https://github.com/sharkdp/bat)**
  is not a tool for notebooks specifically.
  But similar to nbpreview,
  it provides a rich output for many types of files on the terminal,
  and is the primary inspiration for nbpreview.
- **[euporie](https://github.com/joouha/euporie)**
  is a really exciting project
  that allows you to edit and run Jupyter notebooks on the terminal.
- **[nbclient](https://github.com/jupyter/nbclient)**
  is a library for executing notebooks from the command line.
- **[nbqa](https://github.com/nbQA-dev/nbQA)**
  allows the use of linters and formatters on notebooks.
  It's also used by this project.
- **[jpterm](https://github.com/davidbrochart/jpterm)**
  is and up-and-coming successor to [nbterm]
  which will be accompanied by a web client.
  Looking forward to seeing this develop.
- **[nbtermix](https://github.com/mtatton/nbtermix)**
  is an actively-developed fork of [nbterm].
- **[nbterm](https://github.com/davidbrochart/nbterm)**
  lets you edit and execute Jupyter Notebooks on the terminal.
- **[papermill](https://github.com/nteract/papermill)**
  allows the parameterization and execution of Jupyter Notebooks.

[nbterm]: https://github.com/davidbrochart/nbterm

<!-- complimentary-tools-end -->

## Credits

<!-- credits-start -->

nbpreview relies on a lot of fantastic projects.
Check out the [dependencies] for a complete list of libraries that are leveraged.

Besides the direct dependencies,
there are some other projects that directly enabled the development of nbpreview.

- **[bat]**
  is not explicitly used in this project,
  but served as the primary inspiration.
  This projects strives to be [bat]—but
  for notebooks.
  Many of nbpreview's features and command-line options are directly adopted from [bat].
- **[Hypermodern Python Cookiecutter](https://github.com/cjolowicz/cookiecutter-hypermodern-python)**
  is the template this project was generated on.
  It is a fantastic template that integrates [Poetry](https://python-poetry.org/),
  [Nox](https://nox.thea.codes/en/stable/),
  and [pre-commit](https://pre-commit.com/).
  It's responsible for most of the underlying structure of this project's CI.
- **[justcharts](https://github.com/koaning/justcharts)**
  is used in this project
  to generate the Vega and Vega-Lite charts.

[bat]: https://github.com/sharkdp/bat

<!-- credits-end -->

[dependencies]: https://github.com/paw-lu/nbpreview/blob/main/pyproject.toml
