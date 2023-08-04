"""Struct template."""

__all__ = ["StructTemplateDataType", "StructTemplate"]

from typing import List, Dict, Optional, TYPE_CHECKING

from .base import *
from .struct import Struct, StructDataType
from .callable import BinaryFunction
from acaciamc.error import *
from acaciamc.tools import axe
from acaciamc.mccmdgen.datatype import DefaultDataType

if TYPE_CHECKING:
    from acaciamc.mccmdgen.datatype import Storable

class StructTemplateDataType(DefaultDataType):
    name = "struct_template"

class StructTemplate(AcaciaExpr):
    def __init__(self, name: str, field: Dict[str, "Storable"],
                 bases: List["StructTemplate"], compiler):
        super().__init__(StructTemplateDataType(), compiler)
        self.name = name
        self.bases = bases
        self.field_types = field
        # Merge attributes from ancestors.
        for base in bases:
            for name, type_ in base.field_types.items():
                if name in self.field_types:
                    raise Error(ErrorType.SFIELD_MULTIPLE_DEFS, attr=name)
                self.field_types[name] = type_
        # Create the function that gets called when this template is
        # called.
        decorators = [axe.chop, axe.star]
        for name, type_ in self.field_types.items():
            decorators.append(axe.arg(name, type_, default=None))
        def _call_self(compiler, **fields: Optional[AcaciaExpr]) -> CALLRET_T:
            res = Struct.from_template(self, self.compiler)
            cmds = []
            for name, value in fields.items():
                if value is not None:
                    cmds.extend(value.export(res.vars[name]))
            return res, cmds
        decorators.reverse()
        for decorator in decorators:
            _call_self = decorator(_call_self)
        self.call_me = BinaryFunction(_call_self, self.compiler)

    def call(self, args: ARGS_T, kwds: KEYWORDS_T):
        """
        Calling a struct template will return a struct. Only keyword
        arguments are allowed to give initial values to fields.
        """
        return self.call_me.call(args, kwds)

    def datatype_hook(self):
        return StructDataType(template=self)

    def is_subtemplate_of(self, template: "StructTemplate") -> bool:
        """Return whether `template` is sub-template of this.
        This itself is treated as its own sub-template.
        """
        if template is self:
            return True
        if template in self.bases:
            return True
        return any(base.is_subtemplate_of(template) for base in self.bases)