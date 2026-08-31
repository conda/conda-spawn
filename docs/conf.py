# SPDX-License-Identifier: BSD-3-Clause
# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = html_title = "conda-spawn"
copyright = "2024, conda-spawn contributors"
author = "conda-spawn contributors"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "myst_parser",
    "sphinx_sitemap",
    "sphinx_design",
    "sphinx_copybutton",
    "sphinxcontrib.programoutput",
]

myst_heading_anchors = 3
myst_enable_extensions = [
    "colon_fence",
]


templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = "conda_sphinx_theme"
html_static_path = ["_static"]

html_css_files = [
    "css/custom.css",
]

# Serving the robots.txt since we want to point to the sitemap.xml file
html_extra_path = ["robots.txt"]

html_theme_options = {
    "navigation_depth": -1,
    "use_edit_page_button": True,
    "navbar_center": ["navbar_center"],
    "icon_links": [
        {
            "name": "GitHub",
            "url": "https://github.com/conda/conda-spawn",
            "icon": "fa-brands fa-square-github",
            "type": "fontawesome",
        },
        {
            "name": "Zulip",
            "url": "https://conda.zulipchat.com",
            "icon": "_static/element_logo.svg",
            "type": "local",
        },
        {
            "name": "Discourse",
            "url": "https://conda.discourse.group/",
            "icon": "fa-brands fa-discourse",
            "type": "fontawesome",
        },
    ],
}

html_context = {
    "github_user": "conda",
    "github_repo": "conda-spawn",
    "github_version": "main",
    "doc_path": "docs",
}

html_baseurl = "https://conda.github.io/conda-spawn/"

# We don't have a locale set, so we can safely ignore that for the sitemaps.
sitemap_locales = [None]
# We're hard-coding stable here since that's what we want Google to point to.
sitemap_url_scheme = "{link}"
