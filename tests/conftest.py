import pytest

from rstlne import settings


@pytest.fixture(scope="session")
def wheel_spec():
    return settings.load_wheel()


@pytest.fixture(scope="session")
def rules():
    return settings.load_rules()


@pytest.fixture(autouse=True)
def no_real_word_data(request, tmp_path_factory, monkeypatch):
    """Ordinary tests never read data/: the bot falls back to letter frequency. Slow tests read it."""
    if request.node.get_closest_marker("slow") is None:
        monkeypatch.setenv("RSTLNE_DATA", str(tmp_path_factory.mktemp("no-data")))
