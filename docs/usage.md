# Usage

nbpreview has only one required argument—`FILE`—which
expects a Jupyter notebook (`.ipynb`) file path.
`FILE` is a flexible argument.
It can take:

- A Jupyter notebook (`ipynb`) file path
- Multiple notebook paths
- Take in intput from stdin

For more details,
see [features].

nbpreview also comes with a convenient alias—`nbp`.
Invoke either `nbpreview`

```console
% nbpreview notebook.ipynb
```

or `nbp`

```console
% nbp notebook.ipynb
```

on the command-line to run the program.

To read the documentation on all options,
their effects,
values,
and environmental variables,
run

```console
% nbpreview --help
```

```{eval-rst}
.. click:: nbpreview.__main__:typer_click_object
   :prog: nbpreview / nbp
   :nested: full
```

[features]: features.md#flexible-file-argument
