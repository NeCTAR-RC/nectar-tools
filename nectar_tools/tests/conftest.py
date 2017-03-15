import pytest


def pytest_pycollect_makemodule(path, parent):
    """Dynamically creates mock fixtures for the current module.

    Provide a list of module/function paths in the `pytest_mock_fixtures`
    attribute of the test module:

    pytest_mock_fixtures = [
        'module.function_name',
    ]

    This becomes equivalent to:

    @pytest.fixture
    def function_name(mocker):
        return mocker.patch('module.function_name')

    So you can use the mock in a test fixture like this:

    def test_something(function_name):
        function_name.return_value = [1, 2, 3]
        call_something()
        function_name.assert_called_with(...)

    Requires pytest-mock.

    """
    module = path.pyimport()
    try:
        mocks = module.pytest_mock_fixtures
    except AttributeError:
        return

    for m in mocks:
        _, name = m.rsplit('.', 1)

        def _make_fixture(function_path, name):
            @pytest.fixture(scope='function')
            def dummy(mocker):
                return mocker.patch(function_path)
            dummy.__name__ = name
            return dummy
        if getattr(module, name, None) is not None:
            raise AttributeError('Mock fixture name aliases existing module '
                                 'attribute "%s" in module "%s".' %
                                 (name, module.__name__))
        setattr(module, name, _make_fixture(m, name))

    return pytest.Module(path, parent)
