"""Entity template of Acacia."""

__all__ = ["ETemplateDataType", "EntityTemplate"]

from typing import List, Tuple, Dict, Union, Any, Optional, TYPE_CHECKING
from abc import ABCMeta, abstractmethod
import itertools

from acaciamc.error import *
from acaciamc.mccmdgen.datatype import DefaultDataType, Storable
from .base import *
from .entity import EntityReference
from .functions import BoundMethodDispatcher, BoundMethod, InlineFunction
from .string import String
from .none import NoneDataType
from .position import Position

if TYPE_CHECKING:
    from acaciamc.compiler import Compiler
    from acaciamc.mccmdgen.datatype import DataType
    from .functions import METHODDEF_T
    from .entity import _EntityBase

class ETemplateDataType(DefaultDataType):
    name = 'entity_template'

class _MethodDispatcher(metaclass=ABCMeta):
    @abstractmethod
    def register(self, template: "EntityTemplate",
                 implementation: "METHODDEF_T"):
        pass

    @abstractmethod
    def register_inherit(self, template: "EntityTemplate",
                         parent: "EntityTemplate"):
        pass

    @abstractmethod
    def bind_to(self, entity: "_EntityBase") -> AcaciaExpr:
        pass

    @abstractmethod
    def bind_to_cast(self, entity: "_EntityBase") -> AcaciaExpr:
        pass

def _check_overload_impl(
        method_name: str,
        implementation: "METHODDEF_T") -> Union[None, Error]:
    """Check if implementation can be used in an overload."""
    err = None
    if isinstance(implementation, InlineFunction):
        res_type = implementation.result_type
        if res_type is None:
            err = Error(ErrorType.OVERRIDE_RESULT_UNKNOWN,
                        name=method_name)
        elif not isinstance(res_type, Storable):
            err = Error(ErrorType.OVERRIDE_RESULT_UNSTORABLE,
                        name=method_name, type_=str(res_type))
    return err

class _OverloadMethodDispatcher(_MethodDispatcher):
    def __init__(self, method_name: str, compiler: "Compiler"):
        self.compiler = compiler
        self.method_name = method_name
        self.bound: List[BoundMethodDispatcher] = []
        self.temp_n_impl: List[Tuple["EntityTemplate", "METHODDEF_T"]] = []
        self.result_var: Union[VarValue, None] = None

    def register(self, template: "EntityTemplate",
                 implementation: "METHODDEF_T"):
        err = _check_overload_impl(self.method_name, implementation)
        if err is not None:
            raise err
        res_type = implementation.result_type
        assert isinstance(res_type, Storable)
        if self.result_var is None:
            self.result_var = res_type.new_var()
        else:
            if not self.result_var.data_type.matches(res_type):
                raise Error(
                    ErrorType.OVERRIDE_RESULT_MISMATCH,
                    got=str(res_type), expect=str(self.result_var.data_type),
                    name=implementation.name
                )
        self.temp_n_impl.append((template, implementation))
        for bound in self.bound:
            bound.add_implementation(template, implementation)

    def register_inherit(self, template: "EntityTemplate",
                         parent: "EntityTemplate"):
        # XXX this will repeat the whole code that calls implementation
        impl = parent._orig_methods[self.method_name]
        self.register(template, impl)

    def bind_to(self, entity: "_EntityBase"):
        res = BoundMethodDispatcher(entity, self.method_name,
                                    self.result_var, self.compiler)
        self.bound.append(res)
        for template, implementation in self.temp_n_impl:
            res.add_implementation(template, implementation)
        return res

    def bind_to_cast(self, entity: "_EntityBase"):
        candidates = {}
        mro = entity.cast_template.mro_
        for template, implementation in self.temp_n_impl:
            if template in mro:
                candidates[mro.index(template)] = implementation
        implementation = candidates[min(candidates)]
        return BoundMethod(entity, self.method_name,
                           implementation, self.compiler)

class _SimpleMethodDispatcher(_MethodDispatcher):
    """Dispatcher for methods with no overload."""
    def __init__(self, method_name: str, no_overload_err: Error,
                 compiler: "Compiler"):
        self.method_name = method_name
        self.compiler = compiler
        self.no_overload_error = no_overload_err
        self.implementation: Optional["METHODDEF_T"] = None
        self.templates: List["EntityTemplate"] = []

    def register(self, template: "EntityTemplate",
                 implementation: "METHODDEF_T"):
        if self.implementation is not None:
            raise self.no_overload_error
        self.templates.append(template)
        self.implementation = implementation

    def register_inherit(self, template: "EntityTemplate",
                         parent: "EntityTemplate"):
        assert parent in self.templates
        self.templates.append(template)

    def bind_to(self, entity: "_EntityBase"):
        return BoundMethod(
            entity, self.method_name,
            self.implementation, self.compiler
        )

    def bind_to_cast(self, entity: "_EntityBase"):
        assert any(
            template in entity.cast_template.mro_
            for template in self.templates
        )
        return self.bind_to(entity)

def method_dispatcher(
        method_name: str, compiler: "Compiler",
        first_implementation: "METHODDEF_T") -> _MethodDispatcher:
    """Create an appropriate method dispatcher.
    NOTE first_implementation is just for deciding which dispatcher to
    use, this won't register them.
    """
    err = None
    if isinstance(first_implementation, InlineFunction):
        err = _check_overload_impl(method_name, first_implementation)
    if err is None:
        # This inline function specifies a storable result type,
        # and it can be overloaded.
        # OR
        # This function is not inlined so it can be overloaded.
        res = _OverloadMethodDispatcher(method_name, compiler)
    else:
        res = _SimpleMethodDispatcher(method_name, err, compiler)
    return res

class EntityTemplate(AcaciaExpr):
    def __init__(self, name: str,
                 field_types: Dict[str, "DataType"],
                 field_metas: Dict[str, dict],
                 methods: Dict[str, "METHODDEF_T"],
                 parents: List["EntityTemplate"],
                 metas: Dict[str, AcaciaExpr],
                 compiler):
        super().__init__(ETemplateDataType(), compiler)
        self.name = name
        self.parents = parents
        self._orig_metas = {}  # Metas are to be handled below
        self._orig_field_types = field_types
        self._orig_field_metas = field_metas
        self._orig_methods = methods
        self.field_types: Dict[str, "DataType"] = {}
        self.field_metas: Dict[str, dict] = {}
        # methods: sorted in MRO order
        self.methods: \
            List[Tuple[EntityTemplate, Dict[str, "METHODDEF_T"]]] = []
        self.method_dispatchers: Dict[str, _MethodDispatcher] = {}
        self.metas: Dict[str, Any] = {}
        self.mro_: List[EntityTemplate] = [self]  # Method Resolution Order
        # Handle meta
        def _meta_error(name: str, expect: str):
            raise Error(ErrorType.ENTITY_META, meta=name,
                        msg='should be %s, got "%s"'
                        % (expect, str(meta.data_type)))
        # We convert meta `AcaciaExpr`s to Python objects here:
        #  `@type`: str
        #  `@position`: Tuple[List[str], str]  # context, position
        for name, meta in metas.items():
            if name == "type":
                if not isinstance(meta, String):
                    _meta_error(name, "str")
                converted = meta.value
            elif name == "position":
                if isinstance(meta, Position):
                    converted = (meta.context, "~ ~ ~")
                elif isinstance(meta, String):
                    converted = ([], meta.value)
                else:
                    _meta_error(name, "str or Pos")
            elif name == "spawn_event":
                if isinstance(meta, String):
                    converted = meta.value
                elif meta.data_type.matches_cls(NoneDataType):
                    converted = "*"
                else:
                    _meta_error(name, "str or None")
            else:
                raise Error(ErrorType.INVALID_ENTITY_META, meta=name)
            self._orig_metas[name] = converted
        # Runtime identification tag
        # Mark which template an entity is using at runtime.
        # This tag is added to all entities that uses this template
        # *exactly* (i.e. exclude entities that use subtemplate of
        # `self`). This is added when summoning.
        # (See `entity.TaggedEntity.from_template`)
        self.runtime_tag = self.compiler.allocate_entity_tag()
        # Inherit attributes from parents
        ## MRO: We use the same C3 algorithm as Python.
        merge = []
        for parent in self.parents:
            if parent.mro_:
                merge.append(parent.mro_.copy())
        if self.parents:
            merge.append(self.parents.copy())
        while merge:
            for ts in merge.copy():
                candidate = ts[0]
                for ts2 in merge:
                    if candidate in ts2[1:]:
                        break
                else:
                    self.mro_.append(candidate)
                    for ts3 in merge.copy():
                        if candidate in ts3:
                            ts3.remove(candidate)
                            if not ts3:
                                merge.remove(ts3)
                    break
            else:
                raise Error(ErrorType.MRO)
        ## Inherit attributes
        # We reverse MRO here because we want the former ones to
        # override latter ones
        for parent in reversed(self.mro_):
            for attr in itertools.chain(field_types, methods):
                if attr in self.field_types:
                    raise Error(ErrorType.EFIELD_MULTIPLE_DEFS, attr=attr)
            self.metas.update(parent._orig_metas)
            self.methods.insert(0, (parent, parent._orig_methods))
            self.field_types.update(parent._orig_field_types)
            self.field_metas.update(parent._orig_field_metas)
        ## Handle methods
        for method, implementation in methods.items():
            for parent in self.mro_:
                if method in parent.method_dispatchers:
                    # 1. `method` is overriding parent's definition
                    disp = parent.method_dispatchers[method]
                    break
            else:  # 2. First definition of `method` (new method)
                disp = method_dispatcher(
                    method, self.compiler, implementation
                )
            self.method_dispatchers[method] = disp
            disp.register(self, implementation)
        for parent in self.mro_:
            for method, disp in parent.method_dispatchers.items():
                if method not in self.method_dispatchers:
                    # 3. Inherited but not overrided `method`
                    self.method_dispatchers[method] = disp
                    disp.register_inherit(self, parent)

    def register_entity(self, entity: "_EntityBase"):
        # Register attributes to and initialize an entity
        # whose template is self.
        # Every entities MUST call their template's `register_entity`
        assert entity.template is self
        # Convert the stored `methods` into bound method of `entity`
        if entity.cast_template is None:
            for name, disp in self.method_dispatchers.items():
                bound_method_disp = disp.bind_to(entity)
                entity.attribute_table.set(name, bound_method_disp)
        else:
            for name, disp in entity.cast_template.method_dispatchers.items():
                bound_method = disp.bind_to_cast(entity)
                entity.attribute_table.set(name, bound_method)
        # Convert the stored `fields` to attributes of `entity`
        for name, meta in self.field_metas.items():
            type_ = self.field_types[name]
            entity.attribute_table.set(
                name, type_.new_var_as_field(entity, **meta))

    def call(self, args, keywords):
        # Calling an entity template returns an entity, the arguments
        # are passed to __init__ if it exists
        inst, cmds = EntityReference.summon_new(self, self.compiler)
        # Call __init__ if it exists
        initializer = inst.attribute_table.lookup("__init__")
        if initializer:
            res, _cmds = initializer.call(args, keywords)
            cmds.extend(_cmds)
            if not res.data_type.matches_cls(NoneDataType):
                raise Error(ErrorType.INITIALIZER_RESULT,
                            type_=str(inst.data_type))
        return inst, cmds

    def is_subtemplate_of(self, other: "EntityTemplate") -> bool:
        # Return whether `self` is a subtemplate of `other`. A
        # template itself is considered as a subtemplate of itself.
        # other:EntityTemplate
        if self is other:
            return True
        for parent in self.parents:
            if parent.is_subtemplate_of(other):
                return True
        return False
