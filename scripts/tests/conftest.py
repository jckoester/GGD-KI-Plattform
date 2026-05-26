"""Pytest-Fixtures fuer Scraper-Unit-Tests."""

from pathlib import Path
import pytest
from bs4 import BeautifulSoup

FIXTURE_DIR = Path(__file__).parent / 'fixtures'


def load_fixture(name: str) -> BeautifulSoup:
    path = FIXTURE_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} nicht vorhanden — zuerst Schritt 4-1 ausfuehren")
    return BeautifulSoup(path.read_text(encoding='utf-8', errors='replace'), 'lxml')
