"""Stand-in for ``google.colab`` used by ``rerun_notebooks.py`` outside Colab.

Only ``userdata`` is provided. Its ``get(name)`` returns the environment
variable of the same name, so a notebook written against Colab secrets runs
unchanged in a headless environment. The ``google`` directory above this one
has no ``__init__.py`` on purpose: it is a PEP 420 namespace package that
merges with the ``google`` namespace other installed packages provide.

Side effect to keep in mind: ``importlib.util.find_spec("google.colab")``
succeeds while this shim is on ``PYTHONPATH``, so notebooks that use it as an
"am I in Colab" check take the Colab branch.
"""

from . import userdata

__all__ = ["userdata"]
