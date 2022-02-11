# Features

## Flexible `FILE` argument

nbpreview has only one required argument—{option}`FILE <nbpreview FILE>`—which
expects a Jupyter notebook (`.ipynb`) file path.

```console
% nbpreview notebook.ipynb
```

{option}`FILE <nbpreview FILE>` is a flexible argument.
It can take it multiple files,
and will render them all at once.
nbpreview will accept multiple file paths manually listed out,

```console
% nbpreview notebook1.ipynb notebook2.ipynb
```

or a glob that expands to one or more notebook file.

```console
% nbpreview notebooks/*.ipynb
```

{option}`FILE <nbpreview FILE>` also accepts text from stdin
and treats the text as the contents of a notebook file.
This can be used to easily view notebooks from the web[^web_warning] using [curl][curl_manpage][^curl].

```console
% curl https://raw.githubusercontent.com/paw-lu/nbpreview/main/tests/unit/assets/notebook.ipynb |  nbpreview
```

This can even be used to filter cells before rendering them.
For example,
[jq][jq_documentation][^jq] can be used to select only the markdown cells from a notebook.
These cells are then passed on to nbpreview to render.

```console
% jq 'with_entries(if .key == "cells" then .value |= map(select(.cell_type == "markdown")) else . end)' tests/unit/assets/notebook.ipynb | nbp
```

## Smart output

### Automatic plain output

nbpreview is smart about its output.
By default it will strip out decorations—such
as boxes, execution counts, and extra spacing—when
its output is piped to stdout.
Making it usable as a preprocessor for other command-line tools.
For example,
if [fgrep][fgrep_manpage][^fgrep] is used to search a notebook file for the string `'parietal'`,
the output can be difficult to parse.

```console
% fgrep parietal notebook.ipynb
       "      <td>parietal</td>\n",
       "      <td>parietal</td>\n",
       "      <td>parietal</td>\n",
       "      <td>parietal</td>\n",
       "      <td>parietal</td>\n",
       "0     s13         18  stim  parietal -0.017552\n",
       "1      s5         14  stim  parietal -0.080883\n",
       "2     s12         18  stim  parietal -0.081033\n",
       "3     s11         18  stim  parietal -0.046134\n",
       "4     s10         18  stim  parietal -0.037970"
```

Instead,
if the notebook is ran through nbpreview first,
it will process the file before passing onto fgrep,
creating a more human-readable output.

```console
% nbpreview notebook.ipynb | fgrep parietal
0     s13         18  stim  parietal -0.017552
1      s5         14  stim  parietal -0.080883
2     s12         18  stim  parietal -0.081033
3     s11         18  stim  parietal -0.046134
4     s10         18  stim  parietal -0.037970
```

Plain rendering can be manually forced
by using the {option}`--plain <nbpreview --plain>`
(or {option}`-p <nbpreview -p>`)
option,

```console
% nbpreview --plain notebook.ipynb
```

or completely disabled
by using the {option}`--decorated <nbpreview --decorated>`
(or {option}`-d <nbpreview -d>`)
option.

```console
% nbpreview --decorated notebook.ipynb
```

This can be configured
by setting the {ref}`NBPREVIEW_PLAIN <nbpreview-plain-NBPREVIEW_PLAIN>` environmental variable.
For example,
to set the default rendering to be plain,
run:

```console
% export NBPREVIEW_PLAIN=1
```

### Automatic paging

nbpreview will automatically view the output in a pager
if the output is longer than the terminal—which
is often.
Similar to the [automatic plain output](#automatic-plain-output),
this will be automatically disabled when piping to other commands.

Thanks to {func}`Click <click.echo_via_pager>`,
nbpreview attempts to choose a pager than renders the notebook in color.
If the {envvar}`PAGER` environmental variable is set,
nbpreview will use the value as the pager command.
To disable the automatic paging,
use the {option}`--no-paging <nbpreview --no-paging>`
(or {option}`-f <nbpreview -f>`) option.

```console
% nbpreview --no-paging notebook.ipynb
```

Conversely,
to manually force paging,
use the {option}`--paging <nbpreview --paging>`
(or {option}`-g <nbpreview -g>`)
option.
This can be configured by setting
the {ref}`NBPREVIEW_PAGING <nbpreview-paging-NBPREVIEW_PAGING>` environmental variable.

## Syntax highlighting

### Themes

Thanks to [Pygments] and {class}`Rich <rich.syntax.Syntax>`,
nbpreview comes with many different syntax highlighting themes.
They can be applied using the {option}`--theme <nbpreview --theme>`
(or {option}`-t <nbpreview -t>`)
option.
Some themes may clash with the terminal theme,
but `'dark'`—the
default theme—and
`'light'` will match the terminal's colors,
and are the most likely to look best across different terminals.

`````{tab-set}

````{tab-item} material
```{raw} html
---
file: _static/examples/theme_material.html
---
```
````

````{tab-item} dracula
```{raw} html
---
file: _static/examples/theme_dracula.html
---
```
````

````{tab-item} one-dark
```{raw} html
---
file: _static/examples/theme_one_dark.html
---
```
````

````{tab-item} monokai
```{raw} html
---
file: _static/examples/theme_monokai.html
---
```
````

````{tab-item} paraiso-light
```{raw} html
---
file: _static/examples/theme_paraiso_light.html
---
```
````

````{tab-item} rainbow_dash
```{raw} html
---
file: _static/examples/theme_rainbow_dash.html
---
```
````

`````

For a list of all available themes
along with a preview of how they look on the terminal
use the {option}`--list-themes <nbpreview --list-themes>` option.

```console
% nbpreview --list-themes
```

### Cell magic

Certain cell magics may be used to run other languages in a Jupyter Notebook cell.
nbpreview detects the use of these magic commands
and adjusts its syntax highlighting to match it.
For example,
here it switches to bash syntax highlighting when the `%%bash` cell magic is used.

```{raw} html
---
file: _static/examples/cell_magic_syntax_highlight.html
---
```

### Multi-language support

Jupyter Notebooks are not Python exclusive.
nbpreview will detect the usage of other languages—such
as Julia.

```{raw} html
---
file: _static/examples/julia_syntax_highlight.html
---
```

## Markdown rendering

Thanks to {class}`Rich <rich.markdown.Markdown>`,
[markdown-it-py](https://markdown-it-py.readthedocs.io/en/latest/),
and [pylatexenc](https://pylatexenc.readthedocs.io/en/latest/),
nbpreview renders markdown content with some extensions.
In addition to typical CommonMark,
nbpreview will also render markdown tables,
create clickable hyperlinks
(if its supported by the terminal),
syntax highlight code blocks
(which respect {option}`--theme <nbpreview --theme>`),
and render block math equations.
It will even render images—which
respect {option}`--image-drawing <nbpreview --image-drawing>`.
For example,

````markdown
# Lorem ipsum

Lorem ipsum dolor sit amet,
consectetur **adipiscing** elit,
sed do eiusmod tempor incididunt
ut labore et dolore magna [aliqua](https://github.com/paw-lu/nbpreview).

$$
\alpha \sim \text{Normal(0, 1)}
$$

_Ut enim ad minim veniam_,
quis nostrud exercitation ullamco
Excepteur sint occaecat `cupidatat` non proident,
sunt in culpa qui.

![Turtle](emoji_u1f422.png)

## At ultrices

```python
def add(x: float, y: float) -> float:
    """Add two numbers."""
    return x + y
```

| Lorep | ipsum | doret |
| ----- | ----- | ----- |
| 1     | 2     | 3     |
| 4     | 5     | 6     |
````

renders as

```{raw} html
---
file: _static/examples/markdown.html
---
```

% MyST will not render these properly if they are broken up into multiple lines
[^curl]: [curl][curl_manpage] is a command-line tool to transfer data from servers. In this example it was used to download the file contents from an address.
[^fgrep]: [fgrep][fgrep_manpage] is equivalent to running `grep -F`—which searches an input file for the literal text given.
[^jq]: [jq][jq_documentation] is a command-line JSON processor. Since Jupyter notebook (`ipynb`) files are in a JSON format, it can be used to filter and transform cells.
[^web_warning]: Like always, do not view notebooks from untrusted sources.

[curl_manpage]: https://linux.die.net/man/1/curl
[fgrep_manpage]: https://linux.die.net/man/1/fgrep
[jq_documentation]: https://stedolan.github.io/jq/
[pygments]: https://github.com/pygments/pygments
