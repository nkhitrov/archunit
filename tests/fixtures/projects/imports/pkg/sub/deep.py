import typing
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pkg import star
if typing.TYPE_CHECKING:
    import pkg.sibling
else:
    import json

VALUE = 1


def late():
    from pkg import star
    return lambda: __import__("x")


class Holder:
    def method(self):
        import pkg.sub
