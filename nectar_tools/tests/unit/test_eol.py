import datetime
from unittest import mock

from nectar_tools import eol
from nectar_tools import test


KUBERNETES_RESPONSE = {
    'result': {
        'releases': [
            {
                'name': '1.33',
                'eolFrom': '2026-06-28',
                'isEol': False,
            },
            {
                'name': '1.32',
                'eolFrom': '2026-02-28',
                'isEol': True,
            },
            {
                'name': '0.9',
                'eolFrom': None,
                'isEol': False,
            },
        ]
    }
}


@mock.patch('nectar_tools.eol.requests.get')
class TestProduct(test.TestCase):
    @staticmethod
    def _mock_response(mock_get):
        response = mock.Mock()
        response.json.return_value = KUBERNETES_RESPONSE
        mock_get.return_value = response

    def test_get_release(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        release = product.get_release('v1.32.4')

        self.assertEqual('1.32', release['name'])
        mock_get.assert_called_once_with(
            'https://endoflife.date/api/v1/products/kubernetes', timeout=30
        )

    def test_get_release_no_v_prefix(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        release = product.get_release('1.33.1')

        self.assertEqual('1.33', release['name'])

    def test_get_release_unknown_cycle(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        self.assertIsNone(product.get_release('v1.99.0'))

    def test_get_release_invalid_version(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        self.assertIsNone(product.get_release('garbage'))
        mock_get.assert_not_called()

    def test_get_eol_date(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        self.assertEqual(
            datetime.date(2026, 2, 28), product.get_eol_date('v1.32.4')
        )

    def test_get_eol_date_unknown(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        self.assertIsNone(product.get_eol_date('v1.99.0'))

    def test_get_eol_date_no_eol_from(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        self.assertIsNone(product.get_eol_date('v0.9.1'))

    def test_releases_cached(self, mock_get):
        self._mock_response(mock_get)
        product = eol.Product('kubernetes')

        product.get_release('v1.32.4')
        product.get_release('v1.33.0')

        mock_get.assert_called_once()
