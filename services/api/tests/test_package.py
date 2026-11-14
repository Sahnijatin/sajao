from importlib.metadata import version

import sajao_api


def test_package_is_installed_in_the_workspace() -> None:
    assert sajao_api.__version__ == version("sajao-api")
