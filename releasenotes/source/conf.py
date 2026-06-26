# Copyright (c) 2026 Australian Research Data Commons (ARDC)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, version 3.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

# Configuration file for the Sphinx build that renders the NeCTAR Tools
# release notes from the reno note files under releasenotes/notes/.

# -- Project information -----------------------------------------------------

project = 'NeCTAR Tools'
copyright = '2019, Australian Research Data Commons (ARDC)'
author = 'ARDC Nectar Cloud Services'

# -- General configuration ---------------------------------------------------

extensions = [
    'reno.sphinxext',
]

source_suffix = '.rst'
master_doc = 'index'
language = 'en'
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = 'alabaster'
html_static_path = ['_static']
