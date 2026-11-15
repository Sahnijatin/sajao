from importlib.metadata import version

import sajao_workers


def test_package_is_installed_in_the_workspace() -> None:
    assert sajao_workers.__version__ == version("sajao-workers")
