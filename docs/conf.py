import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.abspath("../src"))

from tsujikiri import __version__

project = "tsujikiri"
author = "kunitoki"
release = __version__
copyright = f"{datetime.now().year}, {author}"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.mathjax",
    "sphinx.ext.viewcode",
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

master_doc = "index"

html_theme = "sphinx_rtd_theme"
html_static_path = []

exclude_patterns = [
    "_build", "dist", "src", "tests", "Thumbs.db", ".DS_Store"]
