"""Helpers for checking product versions against endoflife.date."""

import datetime
import logging
import re

import requests


LOG = logging.getLogger(__name__)

API_URL = 'https://endoflife.date/api/v1/products'

VERSION_RE = re.compile(r'v?(\d+)\.(\d+)')


class Product:
    """Release EOL data for one endoflife.date product.

    Releases are fetched once, on first use, and cached for the life of
    the object.
    """

    def __init__(self, name):
        self.name = name
        self._releases = None

    @property
    def releases(self):
        if self._releases is None:
            response = requests.get(f'{API_URL}/{self.name}', timeout=30)
            response.raise_for_status()
            releases = response.json()['result']['releases']
            self._releases = {r['name']: r for r in releases}
        return self._releases

    def get_release(self, version):
        """Return release data for a version string like v1.32.4.

        The version is matched to its release cycle by major.minor.
        Returns None for versions that don't map to a known release.
        """
        match = VERSION_RE.match(version)
        if not match:
            return None
        return self.releases.get(f'{match.group(1)}.{match.group(2)}')

    def get_eol_date(self, version):
        """Return the EOL date for a version, or None if unknown."""
        release = self.get_release(version)
        if not release or not release.get('eolFrom'):
            return None
        return datetime.date.fromisoformat(release['eolFrom'])
