"""Was jedes Mitglied einer Gruppe lesen darf (0.20, Päckchen AC, F6)."""
import pytest

from app.context.visibility import fuer_gruppe_lesbar


@pytest.mark.parametrize("scope", ["global", "school", "subject"])
def test_offene_scopes(scope):
    assert fuer_gruppe_lesbar(scope, None, 7)


def test_eigene_gruppe_ja_fremde_nein():
    assert fuer_gruppe_lesbar("group", 7, 7)
    assert not fuer_gruppe_lesbar("group", 8, 7)


@pytest.mark.parametrize("scope", ["private", "group_teachers", None])
def test_nicht_fuer_alle(scope):
    """Privates und Planungsknoten der Lehrkräfte — auch der eigenen Gruppe — bleiben draußen."""
    assert not fuer_gruppe_lesbar(scope, 7, 7)
