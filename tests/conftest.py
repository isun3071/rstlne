import pytest

from wof import settings


@pytest.fixture(scope="session")
def wheel_spec():
    return settings.load_wheel()


@pytest.fixture(scope="session")
def rules():
    return settings.load_rules()
