"""Builtin float point values."""

__all__ = ["Float"]

from functools import partialmethod

from .base import *
from .types import DataType, FloatType
from .integer import IntLiteral

class Float(AcaciaExpr):
    def __init__(self, value: float, compiler):
        super().__init__(DataType.from_type_cls(FloatType, compiler), compiler)
        self.value = value

    @classmethod
    def from_int(cls, integer: IntLiteral):
        return Float(float(integer.value), integer.compiler)

    def __str__(self) -> str:
        return str(self.value)

    def __pos__(self):
        return self

    def __neg__(self):
        return Float(-self.value, self.compiler)

    def _bin_op(self, other, method: str):
        """`method`: "__add__", "__sub__", etc."""
        if isinstance(other, (Float, IntLiteral)):
            return Float(getattr(self.value, method)(other.value),
                         self.compiler)
        return NotImplemented

    __add__ = partialmethod(_bin_op, method="__add__")
    __sub__ = partialmethod(_bin_op, method="__sub__")
    __mul__ = partialmethod(_bin_op, method="__mul__")
    __floordiv__ = partialmethod(_bin_op, method="__floordiv__")
    __mod__ = partialmethod(_bin_op, method="__mod__")
    __radd__ = partialmethod(_bin_op, method="__radd__")
    __rsub__ = partialmethod(_bin_op, method="__rsub__")
    __rmul__ = partialmethod(_bin_op, method="__rmul__")
    __rfloordiv__ = partialmethod(_bin_op, method="__rfloordiv__")
    __rmod__ = partialmethod(_bin_op, method="__rmod__")