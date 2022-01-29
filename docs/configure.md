# Configure

Every option in {program}`nbpreview` has an associated environmental variable
that can be set to provide a default value.
For example,
to set the theme to `'material'`,
run:

```console
% nbpreview --theme='material' notebook.ipynb
```

To apply the `'material'` theme
without having to specify it in the {option}`--theme <nbpreview --theme>` option,
set the environmental variable associated with the command-line option.
The environmental variables for each option
are explicitly listed at the end of the [command-line usage].
They may also be found in the {option}`--help` message under `env var:`.

```console
% nbpreview --help
⋮
  -t, --theme
                                  The theme to use for syntax highlighting.
                                  Call '--list-themes' to preview all
                                  available themes.  [env var:
                                  NBPREVIEW_THEME; default: dark]
```

In the case of {option}`--theme <nbpreview --theme>`,
the environmental variable is {ref}`NBPREVIEW_THEME <nbpreview-theme-NBPREVIEW_THEME>`.
Set it by running

```console
% export NBPREVIEW_THEME='material'
```

Now, whenever nbpreview is run,
it will automatically set the {option}`--theme <nbpreview --theme>` value to `'material'`.
To set this permanently,
set the environmental variable in the shell's startup file—such as
`~/.zshrc`, `~/.zshenv`, `~/.bashrc`, `~/.bash_profile`, etc.
Environmental variables set the new default for nbpreview,
but they can still be overridden anytime by manually the relevant command-line option.

[command-line usage]: usage
