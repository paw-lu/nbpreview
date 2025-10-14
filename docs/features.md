# Features

## Flexible `FILE` argument

nbpreview has only one required argument—{option}`FILE <nbpreview FILE>`—which
expects a Jupyter notebook (`.ipynb`) file path.

```console
% nbpreview notebook.ipynb
```

{option}`FILE <nbpreview FILE>` is a flexible argument.
It can take in multiple files
and render them all at once.
nbpreview will accept multiple file paths manually listed out,

```console
% nbpreview notebook1.ipynb notebook2.ipynb
```

or a glob that expands to one or more notebook files.

```console
% nbpreview notebooks/*.ipynb
```

{option}`FILE <nbpreview FILE>` also accepts text from stdin
and treats it as the contents of a notebook file.
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
This makes nbpreview usable as a preprocessor for other command-line tools.
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
if the notebook is run through nbpreview first,
it will process the file before passing it onto fgrep,
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
nbpreview attempts to choose a pager that renders the notebook in color.
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
`'light'` will match the terminal's colors.

`````{tab-set}

````{tab-item} material
```{raw} html
---
file: _static/examples/html/theme_material.html
---
```
````

````{tab-item} dracula
```{raw} html
---
file: _static/examples/html/theme_dracula.html
---
```
````

````{tab-item} one-dark
```{raw} html
---
file: _static/examples/html/theme_one_dark.html
---
```
````

````{tab-item} monokai
```{raw} html
---
file: _static/examples/html/theme_monokai.html
---
```
````

````{tab-item} paraiso-light
```{raw} html
---
file: _static/examples/html/theme_paraiso_light.html
---
```
````

````{tab-item} rainbow_dash
```{raw} html
---
file: _static/examples/html/theme_rainbow_dash.html
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
file: _static/examples/html/cell_magic_syntax_highlight.html
---
```

### Multi-language support

Jupyter Notebooks are not Python exclusive.
nbpreview will detect the usage of other languages—such
as Julia.

```{raw} html
---
file: _static/examples/html/julia_syntax_highlight.html
---
```

### Wrapping and line numbers

Depending on your terminal size,
code cell contents might be too long to fit on the terminal.
By default,
nbpreview truncates the long code.
But if {option}`--code-wrap <nbpreview --code-wrap>`
(or {option}`-q <nbpreview -q>`)
is used,
nbpreview will wrap the code around so that it's all visible.
It's usually best to use this will {option}`--line-numbers <nbpreview --line-numbers>`
(or {option}`-m <nbpreview -m>`)
to enable line numbers—so
that wrapping is clearly distinguished from a line break.

```{raw} html
---
file: _static/examples/html/long_code.html
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
(if it's supported by the terminal),
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
file: _static/examples/html/markdown.html
---
```

## Images

Thanks to [Picharsso]
and {class}`term-image <term_img.image.BlockImage>`,
nbpreview renders images.

### Drawing types

The {option}`--image-drawing <nbpreview --image-drawing>`
(or {option}`--id <nbpreview --id>`)
option can be used to control the method nbpreview uses to draw images.

`````{tab-set}

````{tab-item} block
```{raw} html
---
file: _static/examples/html/images_block.html
---
```
````

````{tab-item} character
```{raw} html
---
file: _static/examples/html/images_character.html
---
```
````

````{tab-item} braille
```{raw} html
---
file: _static/examples/html/images_braille.html
---
```
````

`````

### Negative and positive space

By default,
nbpreview draws figures in negative space—meaning
characters are used to draw the dark portions of the image.
This works well as a default since most charts have a light background by default.
However, when working with darker images—like
if a dark theme is being used on a plot—the
drawing can be switched to positive space
using the {option}`--positive-space <nbpreview --positive-space>`
(or {option}`-s <nbpreview -s>`)
option.

```{attention}
{option}`--positive-space <nbpreview --positive-space>`
only works on {option}`--image-drawing='character' <nbpreview --image-drawing>`.
{option}`--image-drawing='braille' <nbpreview --image-drawing>`
only draws in positive space.
```

`````{tab-set}

````{tab-item} character (positive space)
```{raw} html
---
file: _static/examples/html/dark_plot_positive_character.html
---
```
````

````{tab-item} character (negative space)
```{raw} html
---
file: _static/examples/html/dark_plot_negative_character.html
---
```
````

````{tab-item} braille
```{raw} html
---
file: _static/examples/html/dark_plot_braille.html
---
```
````

````{tab-item} block
```{raw} html
---
file: _static/examples/html/dark_plot_block.html
---
```

````

`````

### Enabling and disabling image rendering

By default,
nbpreview will attempt to detect
if images can be viewed on the terminal.
This can be manually controlled via the
{option}`--images <nbpreview --images>`
or {option}`--no-images <nbpreview --no-images>`
options.

```{caution}
Rendering images can impact nbpreview's performance—especially
if the notebook contains many images.
The drawing type selected
via {option}`--image-drawing <nbpreview --image-drawing>`
can play a role in how severe the performance impact is.
```

## DataFrame rendering

Thanks to {class}`Rich <rich.table.Table>`
and {class}`lxml <lxml.html.HtmlElement>`,
nbpreview renders Pandas DataFrame as a table.

```{raw} html
---
file: _static/examples/html/dataframe.html
---
```

## Vega and VegaLite charts

nbpreview will renderer static previews of [Vega and VegaLite charts][vega_example]
along with a link to an interactive version (thanks to [justcharts]).

```{raw} html
---
file: _static/examples/html/vega.html
---
```

## $\LaTeX$

Thanks to {class}`pylatexenc <pylatexenc.latex2text.LatexNodes2Text>`,
nbpreview can render $\LaTeX$ as unicode characters.

```{raw} html
---
file: _static/examples/html/latex.html
---
```

## HTML

Thanks to [html2text],
nbpreview renders basic HTML.
It will also generate a link to the output
so it can be easily previewed in the browser.

```{raw} html
---
file: _static/examples/html/html.html
---
```

## Hyperlinks

With certain complex content—such
as images
and HTML—nbpreview
will display hyperlinks to them in the render.

```{raw} html
---
file: _static/examples/html/links.html
---
```

The hyperlinks will only work if supported by the terminal.
nbpreview attempts to detect this,
but it can be manually controlled
through the {option}`--hyperlinks <nbpreview --hyperlinks>`
or {option}`--no-hyperlinks <nbpreview --no-hyperlinks>` options.
If hyperlinks are not enabled,
the link address will instead be directly printed to the terminal
so that it's easy to click or copy.

By default,
nbpreview displays a hint message
that prompts the user to click on the link.
These hints may be removed
by using the {option}`--hide-hyperlink-hints <nbpreview --hide-hyperlink-hints>`
(or {option}`-y <nbpreview -y>`)
option.

To create previews,
nbpreview will write the content to temporary files
as the notebook is rendered.
To prevent nbpreview from writing files to your machine,
use the {option}`--no-files <nbpreview --no-files>`
(or {option}`-l <nbpreview -l>`)
option.

## Nerd Fonts

By default,
nbpreview uses emoji to highlight certain content
([like clickable links][hyperlinks]).
Instead of using emoji,
nbpreview also supports using icons from [Nerd Fonts][nerd fonts][^nerd_fonts].
Simply use the {option}`--nerd-font <nbpreview --nerd-font>` option
to enable them.

```{attention}
You'll need to have a [Nerd Font][nerd fonts] installed and applied
to your terminal to view the Nerd Font icons—or
else you'll get tofu (`􏿾`) characters where the icons should be.
```

## Stderr

Similar to Jupyter Notebooks,
stderr text is highlighted in a bright red box.

```{raw} html
---
file: _static/examples/html/stderr.html
---
```

## Tracebacks

Tracebacks are rendered with syntax highlighting.

```{raw} html
---
file: _static/examples/html/traceback.html
---
```

% MyST will not render these properly if they are broken up into multiple lines
[^curl]: [curl][curl_manpage] is a command-line tool to transfer data from servers. In this example it was used to download the file contents from an address.
[^fgrep]: [fgrep][fgrep_manpage] is equivalent to running `grep -F`—which searches an input file for the literal text given.
[^jq]: [jq][jq_documentation] is a command-line JSON processor. Since Jupyter notebook (`ipynb`) files are in a JSON format, it can be used to filter and transform cells.
[^nerd_fonts]: [Nerd Fonts] are fonts patched with support for extra icons.
[^web_warning]: Like always, do not view notebooks from untrusted sources.

[curl_manpage]: https://linux.die.net/man/1/curl
[fgrep_manpage]: https://linux.die.net/man/1/fgrep
[html2text]: http://alir3z4.github.io/html2text/
[hyperlinks]: #hyperlinks
[jq_documentation]: https://stedolan.github.io/jq/
[justcharts]: https://github.com/koaning/justcharts
[nerd fonts]: https://www.nerdfonts.com/
[picharsso]: https://kelvindecosta.github.io/picharsso/
[pygments]: https://github.com/pygments/pygments
[vega_example]: https://github.com/jupyterlab/jupyterlab/blob/master/examples/vega/vega-extension.ipynb
