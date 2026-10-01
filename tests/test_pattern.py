import pytest

from archunit.core.pattern import PackagePattern


@pytest.mark.parametrize(
    ("pattern", "name", "expected"),
    [
        ("shop.di", "shop.di", True),
        ("shop.di", "shop.di.x", False),
        ("shop..", "shop", True),
        ("shop..", "shop.a.b", True),
        ("shop..", "shopping", False),
        ("..domain..", "domain", True),
        ("..domain..", "a.domain.b", True),
        ("..domain..", "a.domains", False),
        ("..domain", "a.b.domain", True),
        ("..domain", "a.domain.b", False),
        ("shop.*", "shop.api", True),
        ("shop.*", "shop", False),
        ("shop.*", "shop.api.v1", False),
        ("shop.*..", "shop.api.v1", True),
        ("shop.*..", "shop", False),
        ("a..b", "a.b", True),
        ("a..b", "a.x.y.b", True),
        ("a..b", "a.b.c", False),
        ("a..b..", "a.x.b.y", True),
    ],
)
def test_matches(pattern: str, name: str, expected: bool) -> None:
    assert PackagePattern(pattern).matches(name) is expected


@pytest.mark.parametrize("pattern", ["", ".", "...", "a...b", "a.**", "a.1b", "a.b-c", "a. b"])
def test_invalid_pattern_rejected(pattern: str) -> None:
    with pytest.raises(ValueError, match="invalid package pattern"):
        PackagePattern(pattern)
