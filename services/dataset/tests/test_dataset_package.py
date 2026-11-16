from importlib.metadata import version

import sajao_dataset
from sajao_dataset.queries import QUERIES


def test_package_is_installed_in_the_workspace() -> None:
    assert sajao_dataset.__version__ == version("sajao-dataset")


def test_queries_are_unique_and_include_hindi() -> None:
    assert len(set(QUERIES)) == len(QUERIES)
    assert any(any("ऀ" <= ch <= "ॿ" for ch in q) for q in QUERIES)
