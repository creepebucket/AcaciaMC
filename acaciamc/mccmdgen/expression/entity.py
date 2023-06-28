"""Entity of Acacia."""

from ...constants import Config
from ...error import *
from .base import *
from .types import DataType

__all__ = ['TaggedEntity', 'EntityReference']

class _EntityBase(AcaciaExpr):
    def __init__(self, template, compiler, cast_to=None):
        super().__init__(DataType.from_entity(template, compiler), compiler)
        self.cast_template = cast_to
        self.template = template
        self.template.register_entity(self)

    def __str__(self) -> str:
        raise NotImplementedError

    def cast_to(self, template):
        raise NotImplementedError

    def export(self, var: "TaggedEntity"):
        cmds = var.clear()
        cmds.append("tag %s add %s" % (self, var.tag))
        return cmds

class EntityReference(_EntityBase):
    def __init__(self, selector: str, template, compiler, cast_to=None):
        self.selector = selector
        super().__init__(template, compiler, cast_to)

    def __str__(self) -> str:
        return self.selector

    def cast_to(self, template):
        return EntityReference(
            self.selector, self.template, self.compiler, template
        )

class TaggedEntity(_EntityBase, VarValue):
    def __init__(self, template, compiler, cast_to=None):
        self.tag = compiler.allocate_entity_tag()
        super().__init__(template, compiler, cast_to)

    def cast_to(self, template):
        return TaggedEntity(self.template, self.compiler, template)

    @classmethod
    def from_template(cls, template, compiler):
        # Create an entity from the template. Return a 2-tuple.
        # Element 0: the `EntityVar` instance
        # Element 1: `list[str]` that contains initial commands to run
        name = compiler.allocate_entity_name()
        inst = cls(template, compiler)
        # Analyze template meta
        # NOTE meta only works when you create an entity using
        # `Template()` (Since this code is in `from_template` method).
        e_type = Config.entity_type
        e_pos = Config.entity_pos
        for meta, value in template.metas.items():
            if meta == "type":
                # Entity type
                e_type = value
            elif meta == "position":
                # Position to summon the entity
                e_pos = value
        # Allocate an entity name to identify it
        return inst, [
            "summon %s %s %s" % (e_type, name, e_pos),
            "tag @e[name=%s] add %s" % (name, inst.template.runtime_tag),
            "tag @e[name=%s] add %s" % (name, inst.tag)
        ]

    @classmethod
    def from_empty(cls, template, compiler):
        # Create an entity reference (a tag), pointing to no entity.
        return cls(template, compiler)

    def __str__(self) -> str:
        # Return selector of this entity
        return "@e[tag=%s]" % self.tag

    def clear(self) -> list[str]:
        # Clear the reference to entity that the tag is pointing to.
        return ["tag %s remove %s" % (self, self.tag)]
