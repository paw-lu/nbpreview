Usage
=====

.. Environmental variable references do not work when this is a markdown file
.. See https://github.com/executablebooks/MyST-Parser/issues/513

nbpreview has only one required argument—:option:`FILE <nbpreview FILE>`—which
expects a Jupyter notebook (``.ipynb``) file path.
:option:`FILE <nbpreview FILE>` is a flexible argument.
It can take:

* A Jupyter notebook (``ipynb``) file path
* Multiple notebook paths
* Take in input from stdin

For more details,
see `features`_.

nbpreview also comes with a convenient alias—``nbp``.
Invoke either ``nbpreview``

.. code:: console

   % nbpreview notebook.ipynb

or ``nbp``

.. code:: console

   % nbp notebook.ipynb

on the command-line to run the program.

.. option:: --help

To read the documentation on all options,
their effects,
values,
and environmental variables,
run

.. code:: console

   % nbpreview --help

.. click:: nbpreview.__main__:typer_click_object
   :prog: nbpreview
   :nested: full


.. _features: features.html#flexible-file-argument
