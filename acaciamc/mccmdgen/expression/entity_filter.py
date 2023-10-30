"""Entity filter -- builtin support for selectors."""

__all__ = ["EFilterType", "EFilterDataType", "EntityFilter"]

from typing import List, Union, Optional, TYPE_CHECKING
import re

from acaciamc.error import *
from acaciamc.tools import axe, versionlib, method_of
from acaciamc.mccmdgen.mcselector import MCSelector, SELECTORVAR_T
from acaciamc.mccmdgen.datatype import DefaultDataType
import acaciamc.mccmdgen.cmds as cmds
from .base import *
from .types import Type
from .position import PosDataType

if TYPE_CHECKING:
    from .position import Position
    from acaciamc.mccmdgen.cmds import _ExecuteSubcmd

RE_INT = re.compile(r"^[+-]?\s*\d+$")
PLAYER = "player"  # ID of player entity

class IntRange(axe.AnyOf):
    """Accepts a string representing integer range or an integer and
    convert it to Python string.
    """
    def __init__(self):
        super().__init__(axe.LiteralInt(), axe.LiteralString())

    def get_show_name(self) -> str:
        return "integer range"

    @staticmethod
    def check_int(value: str) -> bool:
        return RE_INT.match(value) is not None

    def convert(self, origin: AcaciaExpr) -> str:
        origin_py = super().convert(origin)
        if isinstance(origin_py, int):
            return str(origin_py)
        assert isinstance(origin_py, str)
        origin_py = origin_py.lstrip()
        if origin_py.startswith("!"):
            origin_py = origin_py[1:]
        if ".." in origin_py:
            min_, max_ = origin_py.split("..")
            min_ = min_.strip()
            max_ = max_.strip()
            if not min_ and not max_:
                self.wrong_argument(origin)
            if (min_ and not self.check_int(min_)
                or max_ and not self.check_int(max_)):
                self.wrong_argument(origin)
            return "%s..%s" % (min_, max_)
        else:
            if self.check_int(origin_py):
                return origin_py
            else:
                self.wrong_argument(origin)

class EFilterDataType(DefaultDataType):
    name = "Enfilter"

class EFilterType(Type):
    def do_init(self):
        @method_of(self, "__new__")
        @axe.chop
        def _new(compiler):
            return EntityFilter(compiler)

    def datatype_hook(self):
        return EFilterDataType()

class _EFilterData:
    def __init__(self, tag: Union[str, None], subcmds: List["_ExecuteSubcmd"],
                 selector: MCSelector):
        # tag: temporary tag name (is None for last tuple).
        # subcmds: is list of /execute subcommands.
        # selector: selector.
        self.tag = tag
        self.subcmds = subcmds
        self.selector = selector

    def copy(self):
        return _EFilterData(
            self.tag, self.subcmds.copy(), self.selector.copy()
        )

    def __getitem__(self, index: int):
        if index == 0:
            return self.tag
        elif index == 1:
            return self.subcmds
        elif index == 2:
            return self.selector
        elif isinstance(index, int):
            raise IndexError(index)
        raise TypeError

class EntityFilter(AcaciaExpr, ImmutableMixin):
    def __init__(self, compiler):
        super().__init__(EFilterDataType(), compiler)
        self.context_occupied = False
        self.data: List[_EFilterData] = []
        self._new_data()  # initial data
        self.next_use_new_data = False
        self.cleanup: List[str] = []  # cleanup commands
        self.entity_type: Union[str, None] = None

        @method_of(self, "all_players")
        @axe.chop
        @transform_immutable(self)
        def _all_players(self: EntityFilter, compiler):
            self.need_set_selector_var("a")
            self.entity_type = PLAYER
            return self
        @method_of(self, "random")
        @axe.chop
        @axe.arg("type", axe.Nullable(axe.LiteralString()), default=None,
                 rename="type_")
        @axe.arg("limit", axe.RangedLiteralInt(1, None), default=1)
        @transform_immutable(self)
        def _random(self: EntityFilter, compiler,
                    type_: Optional[str], limit: int):
            selector = self.need_set_selector_var("r")
            if self.entity_type is None:
                if type_ is None:
                    raise axe.ArgumentError(
                        "type", "type can't be omitted when it can't "
                        "be inferred from previous filters"
                    )
                self.entity_type = type_
            else:
                if type_ is not None and self.entity_type != type_:
                    raise axe.ArgumentError(
                        "type", "type mismatch with previous given type"
                        "(%s != %s)" % (type_, self.entity_type)
                    )
            if not selector.has_arg("type"):
                selector.type(type_)
            selector.limit(limit)
            # There should be a difference between these two:
            # (Supporse there are more than 5 entities with name "xxx")
            #  Enfilter().is_name("xxx").random("t", limit=5)
            #   Selects 5 random entities with name "xxx"
            #   i.e. Selects @r[type=t, c=5, name=xxx]
            #  Enfilter().random("t", limit=5).is_name("xxx")
            #   Selects at most 5 random entities with name "xxx"
            #   i.e. tag @r[type=t, c=5] add tmp
            #        Selects @e[name=xxx, tag=tmp]
            # Thus, we do not accept more arguments for @r selector
            # now (the same for nearest_from and farthest_from):
            self.next_use_new_data = True
            return self
        @method_of(self, "nearest_from")
        @axe.chop
        @axe.arg("origin", PosDataType)
        @axe.arg("limit", axe.RangedLiteralInt(1, None), default=1)
        @transform_immutable(self)
        def _nearest_from(self: EntityFilter, compiler,
                          origin: "Position", limit: int):
            self.need_set_selector_var("e")
            selector = self.need_set_context(*origin.context)
            selector.limit(limit)
            self.next_use_new_data = True  # see `_random` above
            return self
        @method_of(self, "farthest_from")
        @axe.chop
        @axe.arg("origin", PosDataType)
        @axe.arg("limit", axe.RangedLiteralInt(1, None), default=1)
        @transform_immutable(self)
        def _farthest_from(self: EntityFilter, compiler,
                           origin: "Position", limit: int):
            self.need_set_selector_var("e")
            selector = self.need_set_context(*origin.context)
            selector.limit(-limit)
            self.next_use_new_data = True  # see `_random` above
            return self
        @method_of(self, "has_tag")
        @axe.chop
        @axe.star_arg("tags", axe.LiteralString())
        @transform_immutable(self)
        def _has_tag(self: EntityFilter, compiler, tags: List[str]):
            selector = self.last_selector()
            selector.tag(*tags)
            return self
        @method_of(self, "has_no_tag")
        @axe.chop
        @axe.star_arg("tags", axe.LiteralString())
        @transform_immutable(self)
        def _has_no_tag(self: EntityFilter, compiler, tags: List[str]):
            selector = self.last_selector()
            selector.tag_n(*tags)
            return self
        @method_of(self, "distance_from")
        @axe.chop
        @axe.arg("origin", PosDataType)
        @axe.arg("min", axe.Nullable(axe.LiteralFloat()), default=None,
                 rename="min_")
        @axe.arg("max", axe.Nullable(axe.LiteralFloat()), default=None,
                 rename="max_")
        @transform_immutable(self)
        def _distance_from(self: EntityFilter, compiler,
                           origin: "Position", min_: Optional[float],
                           max_: Optional[float]):
            selector = self.need_set_context(*origin.context)
            selector.distance(min_, max_)
            return self
        @method_of(self, "is_type")
        @axe.chop
        @axe.arg("type", axe.LiteralString(), rename="type_")
        @transform_immutable(self)
        def _is_type(self: EntityFilter, compiler, type_: str):
            selector = self.new_if_got("type")
            selector.type(type_)
            self.entity_type = type_
            return self
        @method_of(self, "is_not_type")
        @axe.chop
        @axe.star_arg("types", axe.LiteralString())
        @transform_immutable(self)
        def _is_not_type(self: EntityFilter, compiler, types: List[str]):
            selector = self.last_selector()
            selector.type_n(*types)
            return self
        @method_of(self, "inside")
        @axe.chop
        @axe.arg("origin", PosDataType)
        @axe.arg("dx", axe.LiteralFloat(), default=0.0)
        @axe.arg("dy", axe.LiteralFloat(), default=0.0)
        @axe.arg("dz", axe.LiteralFloat(), default=0.0)
        @transform_immutable(self)
        def _inside(self: EntityFilter, compiler,
                    origin: "Position", dx: int, dy: int, dz: int):
            selector = self.need_set_context(*origin.context)
            selector.volume(dx, dy, dz)
            return self
        @method_of(self, "rot_vertical")
        @axe.chop
        @axe.arg("min", axe.LiteralFloat(), default=-90.0, rename="min_")
        @axe.arg("max", axe.LiteralFloat(), default=90.0, rename="max_")
        @transform_immutable(self)
        def _rot_vertical(self: EntityFilter, compiler,
                          min_: float, max_: float):
            selector = self.new_if_got("rx", "rxm")
            selector.rot_vertical(min_, max_)
            return self
        @method_of(self, "rot_horizontal")
        @axe.chop
        @axe.arg("min", axe.LiteralFloat(), default=-180.0, rename="min_")
        @axe.arg("max", axe.LiteralFloat(), default=180.0, rename="max_")
        @transform_immutable(self)
        def _rot_horizontal(self: EntityFilter, compiler,
                            min_: float, max_: float):
            selector = self.new_if_got("ry", "rym")
            selector.rot_horizontal(min_, max_)
            return self
        @method_of(self, "is_name")
        @axe.chop
        @axe.arg("name", axe.LiteralString())
        @transform_immutable(self)
        def _is_name(self: EntityFilter, compiler, name: str):
            selector = self.new_if_got("name")
            selector.name(name)
            return self
        @method_of(self, "is_not_name")
        @axe.chop
        @axe.star_arg("names", axe.LiteralString())
        @transform_immutable(self)
        def _is_not_name(self: EntityFilter, compiler, names: List[str]):
            selector = self.last_selector()
            selector.name_n(*names)
            return self
        @method_of(self, "has_item")
        @axe.chop
        @axe.arg("item", axe.LiteralString())
        @axe.arg("quantity", IntRange(), default="1..")
        @axe.arg("data", axe.Nullable(axe.LiteralInt()), default=None)
        @axe.arg("slot_type", axe.Nullable(axe.LiteralString()), default=None)
        @axe.arg("slot_num", axe.Nullable(IntRange()), default=None)
        @transform_immutable(self)
        def _has_item(self: EntityFilter, compiler, item: str,
                      quantity: str, data: Optional[int],
                      slot_type: Optional[str], slot_num: Optional[int]):
            if slot_type is None and slot_num is not None:
                raise axe.ArgumentError("slot_num", "should be None when "
                                        "slot_type is None")
            selector = self.last_selector()
            selector.has_item(item, quantity, data, slot_type, slot_num)
            return self
        @method_of(self, "scores")
        @axe.chop
        @axe.arg("objective", axe.LiteralString())
        @axe.arg("range", IntRange(), rename="range_")
        @transform_immutable(self)
        def _scores(self: EntityFilter, compiler, objective: str,
                    range_: str):
            selector = self.last_selector()
            selector.scores(objective, range_)
            return self
        @method_of(self, "level")
        @axe.chop
        @axe.arg("min", axe.Nullable(axe.LiteralInt()),
                 default=None, rename="min_")
        @axe.arg("max", axe.Nullable(axe.LiteralInt()),
                 default=None, rename="max_")
        @transform_immutable(self)
        def _level(self: EntityFilter, compiler, min_: Optional[int],
                   max_: Optional[int]):
            selector = self.new_if_got("l", "lm")
            selector.level(min_, max_)
            self.entity_type = PLAYER
            return self
        @method_of(self, "is_game_mode")
        @axe.chop
        @axe.arg("mode", axe.LiteralString())
        @transform_immutable(self)
        def _is_game_mode(self: EntityFilter, compiler, mode: str):
            selector = self.last_selector()
            selector.game_mode(mode)
            self.entity_type = PLAYER
            return self
        @method_of(self, "is_not_game_mode")
        @axe.chop
        @axe.star_arg("modes", axe.LiteralString())
        @transform_immutable(self)
        def _is_not_game_mode(self: EntityFilter, compiler, modes: List[str]):
            selector = self.last_selector()
            selector.game_mode_n(*modes)
            self.entity_type = PLAYER
            return self
        @method_of(self, "has_permission")
        @versionlib.only(versionlib.at_least((1, 19, 80)))
        @axe.chop
        @axe.star_arg("permissions", axe.LiteralString())
        @transform_immutable(self)
        def _has_permission(self: EntityFilter, compiler,
                            permissions: List[str]):
            selector = self.last_selector()
            selector.has_permission(*permissions)
            self.entity_type = PLAYER
            return self
        @method_of(self, "has_no_permission")
        @versionlib.only(versionlib.at_least((1, 19, 80)))
        @axe.chop
        @axe.star_arg("permissions", axe.LiteralString())
        @transform_immutable(self)
        def _has_no_permission(self: EntityFilter, compiler,
                               permissions: List[str]):
            selector = self.last_selector()
            selector.has_permission_n(*permissions)
            self.entity_type = PLAYER
            return self

    def copy(self):
        res = EntityFilter(self.compiler)
        res.data = [data.copy() for data in self.data]
        res.context_occupied = self.context_occupied
        res.next_use_new_data = self.next_use_new_data
        res.cleanup = self.cleanup.copy()
        res.entity_type = self.entity_type
        return res

    def dump(self, command: str, among_tag: Optional[str] = None) -> CMDLIST_T:
        """
        Select entities filtered by this filter and return commands.
        The command can have "{selected}" placeholder, which will be
        replaced by the selected entity.
        When `among_tag` is specified, the filter will begin selecting
        among entities with that tag, instead of all entities.
        """
        res = []
        last_tag = among_tag
        for tag, subcmds, selector in self.data[:-1]:
            if last_tag is not None:
                selector = selector.copy()
                selector.tag(last_tag)
            res.append(cmds.Execute(
                subcmds,
                runs=cmds.Cmd("tag %s add %s" % (selector.to_str(), tag))
            ))
            last_tag = tag
        _, final_subcmds, final_selector = self.data[-1]
        if last_tag is not None:
            final_selector = final_selector.copy()
            final_selector.tag(last_tag)
        res.append(cmds.Execute(
            final_subcmds, command.format(selected=final_selector.to_str())
        ))
        res.extend(self.cleanup)
        return res

    def need_set_selector_var(self, var: SELECTORVAR_T) -> MCSelector:
        if self.data[-1].selector.is_var_set():
            self._new_data()
        res = self.data[-1].selector
        res.var = var
        return res

    def need_set_context(self, *context: "_ExecuteSubcmd") -> MCSelector:
        if self.context_occupied:
            self._new_data()
        self.data[-1].subcmds.extend(context)
        self.context_occupied = True
        return self.data[-1].selector

    def last_selector(self) -> MCSelector:
        if self.next_use_new_data:
            self._new_data()
        return self.data[-1].selector

    def new_if_got(self, *args: str) -> MCSelector:
        selector = self.last_selector()
        if any(selector.has_arg(a) for a in args):
            self._new_data()
        return self.data[-1].selector

    def _new_data(self):
        if self.data:
            # Handle last data
            tag = self.compiler.allocate_entity_tag()
            self.data[-1].tag = tag
            self.cleanup.append("tag @e[tag={0}] remove {0}".format(tag))
        self.data.append(_EFilterData(None, [], MCSelector()))
        self.context_occupied = False
        self.next_use_new_data = False
