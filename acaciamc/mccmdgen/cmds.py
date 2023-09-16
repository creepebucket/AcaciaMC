"""Abstraction of Minecraft commands."""

from abc import ABCMeta, abstractmethod
from enum import Enum
from copy import deepcopy
from typing import List, NamedTuple, Optional, Union, Iterable, Callable, Dict
import json

from acaciamc.constants import Config

_TERMINATOR_CHARS = frozenset(" ,@~^/$&\"'!#%+*=[{]}\\|<>`\n")

def mc_str(s: str) -> str:
    if not s:
        return '""'
    if any(char in _TERMINATOR_CHARS for char in s):
        return '"%s"' % "".join(
            "\\\\" if char == "\\" else
            "\\\"" if char == '"' else
            char
            for char in s
        )
    else:
        return s

def mc_selector(s: str) -> str:
    if s.startswith("@"):
        return s
    else:
        return mc_str(s)

def mc_wc_selector(s: str) -> str:
    if s == "*":
        return s
    else:
        return mc_selector(s)

class ScbSlot(NamedTuple):
    target: str
    objective: str

    def to_str(self) -> str:
        return "%s %s" % (
            mc_wc_selector(self.target),
            mc_str(self.objective)
        )

    def is_selector(self) -> bool:
        """Return whether the slot target is selector or wildcard."""
        return self.target.startswith("@") or self.target == "*"

class Command(metaclass=ABCMeta):
    @abstractmethod
    def resolve(self) -> str:
        pass

    def func_ref(self) -> Optional["MCFunctionFile"]:
        return None

    def scb_replace(
            self, origin: ScbSlot, target: ScbSlot
        ) -> Optional["Command"]:
        return None

    def scb_did_read(self, slot: ScbSlot) -> bool:
        """Did read the slot or not?"""
        return False

    def scb_did_assign(self, slot: ScbSlot) -> bool:
        """Did assign to the slot (set, operation =, random) or not?"""
        return False

    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        """Did augmented assign (add, remove, non-"=" operation,
        /execute + assign) the slot or not?
        """
        return False

    def scb_did_read_unreplacable(self, slot: ScbSlot) -> bool:
        """Did call a mcfunction that read the slot or not?"""
        return False

    def __repr__(self) -> str:
        return "<%s %r>" % (type(self).__name__, self.resolve())

class Cmd(Command):
    def __init__(self, cmd: str, suppress_special_cmd=False):
        self.value = cmd
        # Read command name
        for i, char in enumerate(cmd):
            if char in _TERMINATOR_CHARS:
                break
        name = cmd[:i]
        if name in ("scoreboard", "schedule", "execute", "function",
                    "tellraw", "titleraw"):
            if not suppress_special_cmd:
                raise ValueError(
                    "/%s command need to be invoked by special class" % name
                )

    def resolve(self) -> str:
        return self.value

class ScbSetConst(Command):
    def __init__(self, target: ScbSlot, value: int):
        self.target = target
        self.value = value

    def resolve(self) -> str:
        return "scoreboard players set %s %d" % (
            self.target.to_str(), self.value
        )

    def scb_did_assign(self, slot: ScbSlot) -> bool:
        return slot == self.target

class ScbAddConst(Command):
    def __init__(self, target: ScbSlot, value: int):
        self.target = target
        self.value = value

    def resolve(self) -> str:
        return "scoreboard players add %s %d" % (
            self.target.to_str(), self.value
        )

    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        return slot == self.target

class ScbRemoveConst(Command):
    def __init__(self, target: ScbSlot, value: int):
        self.target = target
        self.value = value

    def resolve(self) -> str:
        return "scoreboard players remove %s %d" % (
            self.target.to_str(), self.value
        )

    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        return slot == self.target

class ScbOp(Enum):
    ADD_EQ = "+="
    SUB_EQ = "-="
    MUL_EQ = "*="
    DIV_EQ = "/="
    MOD_EQ = "%="
    SWAP = "><"
    MIN = "<"
    MAX = ">"
    ASSIGN = "="

class ScbOperation(Command):
    def __init__(self, op: ScbOp, operand1: ScbSlot, operand2: ScbSlot):
        self.operator = op
        self.operand1 = operand1
        self.operand2 = operand2

    def resolve(self) -> str:
        return "scoreboard players operation %s %s %s" % (
            self.operand1.to_str(),
            self.operator.value,
            self.operand2.to_str()
        )

    def scb_did_assign(self, slot: ScbSlot) -> bool:
        if self.operator is ScbOp.ASSIGN:
            return slot == self.operand1
        elif self.operator is ScbOp.SWAP:
            return slot == self.operand1 or slot == self.operand2
        else:
            return False

    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        if (self.operator is not ScbOp.ASSIGN
            and self.operator is not ScbOp.SWAP):
            return slot == self.operand1

    def scb_did_read(self, slot: ScbSlot) -> bool:
        if self.operator is ScbOp.SWAP:
            return slot == self.operand1 or slot == self.operand2
        else:
            return slot == self.operand2

    def scb_replace(self, origin: ScbSlot, target: ScbSlot) -> "ScbOperation":
        operand1 = target if origin == self.operand1 else self.operand1
        operand2 = target if origin == self.operand2 else self.operand2
        return ScbOperation(self.operator, operand1, operand2)

class ScbRandom(Command):
    def __init__(self, target: ScbSlot, min_: int, max_: int):
        super().__init__()
        self.target = target
        self.min = min_
        self.max = max_

    def resolve(self) -> str:
        return "scoreboard players random %s %d %d" % (
            self.target.to_str(), self.min, self.max
        )

    def scb_did_assign(self, slot: ScbSlot) -> bool:
        return slot == self.target

class ScbObjAdd(Command):
    def __init__(self, name: str, display_name: Optional[str] = None):
        super().__init__()
        self.name = name
        self.display_name = display_name

    def resolve(self) -> str:
        if self.display_name is None:
            suffix = ""
        else:
            suffix = " %s" % mc_str(self.display_name)
        return "scoreboard objectives add %s dummy%s" % (
            mc_str(self.name), suffix
        )

class ScbObjRemove(Command):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def resolve(self) -> str:
        return "scoreboard objectives remove %s" % mc_str(self.name)

class ScbObjDisplay(Command):
    def __init__(self, location: str, name: Optional[str],
                 order: Optional[str] = None):
        super().__init__()
        if location not in ("sidebar", "list", "belowname"):
            raise ValueError("Invalid location: %s" % location)
        if order is not None and name is not None:
            raise ValueError("Can't specify order when clearing display")
        if order is not None and location == "belowname":
            raise ValueError("Can't specify order for belowname")
        self.name = name
        self.location = location
        self.order = order

    def resolve(self) -> str:
        order = " %s" % self.order if self.order else ""
        scb = "" if self.name is None else " %s" % mc_str(self.name)
        return "scoreboard objectives setdisplay %s%s%s" % (
            mc_str(self.location), scb, order
        )

class MCFunctionFile:
    """Represents a .mcfunction file."""
    def __init__(self, path: Optional[str] = None):
        """path: full path to file."""
        self.commands: List[Command] = []
        self.set_path(path)

    def __repr__(self) -> str:
        return "<MCFunctionFile path=%r>" % self._path

    def has_content(self):
        """Return if there are any commands in this file."""
        return any((not isinstance(cmd, Comment)) for cmd in self.commands)

    # --- About Path ---

    def get_path(self):
        if self._path is None:
            raise ValueError('"path" attribute is not set yet')
        return self._path

    def set_path(self, path: str):
        self._path = path

    def is_path_set(self) -> bool:
        return self._path is not None

    # --- Export Methods ---

    def to_str(self) -> str:
        return '\n'.join(cmd.resolve() for cmd in self.commands)

    # --- Write Methods ---

    def write(self, *commands: Union[str, Command]):
        self.extend(commands)

    def write_debug(self, *comments: str):
        if Config.debug_comments:
            self.commands.extend(map(Comment, comments))

    def extend(self, commands: Iterable[Union[str, Command]]):
        for command in commands:
            if isinstance(command, Command):
                self.commands.append(command)
            else:
                self.commands.append(Cmd(command))

class Comment(Command):
    def __init__(self, comment: str):
        if not comment.startswith("#"):
            raise ValueError("Comment must start with '#': %r" % comment)
        self.comment = comment

    def resolve(self) -> str:
        return self.comment

class _InvokeFunction(Command):
    def __init__(self, file: "MCFunctionFile"):
        super().__init__()
        self.file = file

    _inside_scb_check: List[MCFunctionFile] = []

    @staticmethod
    def _scb_check(func: Callable[["_InvokeFunction", ScbSlot], bool]):
        def _wrapped(self: "_InvokeFunction", slot: ScbSlot) -> bool:
            if self.file in self._inside_scb_check:
                return False
            self._inside_scb_check.append(self.file)
            result = func(self, slot)
            self._inside_scb_check.pop()
            return result
        return _wrapped

    def func_ref(self) -> "MCFunctionFile":
        return self.file

    @_scb_check
    def scb_did_assign(self, slot: ScbSlot) -> bool:
        return any(cmd.scb_did_assign(slot) for cmd in self.file.commands)

    @_scb_check
    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        return any(cmd.scb_did_augassign(slot) for cmd in self.file.commands)

    @_scb_check
    def scb_did_read_unreplacable(self, slot: ScbSlot) -> bool:
        return any(
            cmd.scb_did_read(slot) or cmd.scb_did_read_unreplacable(slot)
            for cmd in self.file.commands
        )

class InvokeFunction(_InvokeFunction):
    def resolve(self) -> str:
        return "function %s" % self.file.get_path()

class ScheduleFunction(_InvokeFunction):
    def __init__(self, file: "MCFunctionFile", args: str):
        super().__init__(file)
        self.args = args

    def resolve(self) -> str:
        return "schedule %s %s" % (self.args, self.file.get_path())

class ScbCompareOp(Enum):
    EQ = "="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="

class _ExecuteSubcmd(metaclass=ABCMeta):
    @abstractmethod
    def resolve(self) -> str:
        pass

    def scb_did_read(self, slot: ScbSlot) -> bool:
        return False

    def scb_replace(
            self, origin: ScbSlot, target: ScbSlot
        ) -> Optional["_ExecuteSubcmd"]:
        return None

class ExecuteEnv(_ExecuteSubcmd):
    def __init__(self, cmd: str, args: str):
        if cmd not in ("align", "anchored", "as", "at", "facing",
                       "in", "positioned", "rotated"):
            raise ValueError("Invalid env subcommand: %s" % cmd)
        self.cmd = cmd
        self.args = args

    def resolve(self) -> str:
        return "%s %s" % (self.cmd, self.args)

class ExecuteCond(_ExecuteSubcmd):
    def __init__(self, cond: str, args: str, invert=False):
        if cond not in ("entity", "block", "blocks"):
            raise ValueError("Invalid condition: %s" % cond)
        self.cond = cond
        self.args = args
        self.invert = invert

    def resolve(self) -> str:
        return " ".join(
            ("unless" if self.invert else "if", self.cond, self.args)
        )

class ExecuteScoreComp(_ExecuteSubcmd):
    def __init__(self, operand1: ScbSlot, operand2: ScbSlot,
                 operator: ScbCompareOp, invert=False):
        super().__init__()
        self.operand1 = operand1
        self.operand2 = operand2
        self.operator = operator
        self.invert = invert

    def scb_did_read(self, slot: ScbSlot) -> bool:
        return slot == self.operand1 or slot == self.operand2

    def scb_replace(self, origin: ScbSlot, target: ScbSlot):
        operand1 = target if origin == self.operand1 else self.operand1
        operand2 = target if origin == self.operand2 else self.operand2
        return ExecuteScoreComp(operand1, operand2, self.operator, self.invert)

    def resolve(self) -> str:
        return "%s score %s %s %s" % (
            "unless" if self.invert else "if",
            self.operand1.to_str(),
            self.operator.value,
            self.operand2.to_str()
        )

class ExecuteScoreMatch(_ExecuteSubcmd):
    def __init__(self, operand: ScbSlot, range_: str, invert=False):
        super().__init__()
        self.operand = operand
        self.range = range_
        self.invert = invert

    def scb_did_read(self, slot: ScbSlot) -> bool:
        return slot == self.operand

    def scb_replace(self, origin: ScbSlot, target: ScbSlot):
        operand = target if origin == self.operand else self.operand
        return ExecuteScoreMatch(operand, self.range, self.invert)

    def resolve(self) -> str:
        return "%s score %s matches %s" % (
            "unless" if self.invert else "if",
            self.operand.to_str(),
            self.range
        )

class Execute(Command):
    def __init__(self, subcmds: List[_ExecuteSubcmd],
                 runs: Union[Command, str]):
        # An execute without a "run" subcommand is useless in
        # mcfunctions.
        super().__init__()
        if isinstance(runs, str):
            runs = Cmd(runs)
        self.subcmds: List[_ExecuteSubcmd] = []
        for subcmd in subcmds:
            self.add_subcmd(subcmd)
        if isinstance(runs, Execute):
            self.runs = runs.runs
            for subcmd in runs.subcmds:
                self.add_subcmd(subcmd)
        else:
            self.runs = runs

    def add_subcmd(self, subcmd: _ExecuteSubcmd):
        self.subcmds.append(subcmd)

    def resolve(self) -> str:
        if not self.subcmds:
            return self.runs.resolve()
        return "execute %s run %s" % (
            " ".join(sub.resolve() for sub in self.subcmds),
            self.runs.resolve()
        )

    def scb_did_read(self, slot: ScbSlot) -> bool:
        return (any(subcmd.scb_did_read(slot) for subcmd in self.subcmds)
                or self.runs.scb_did_read(slot))

    def scb_did_augassign(self, slot: ScbSlot) -> bool:
        return (self.runs.scb_did_assign(slot)
                or self.runs.scb_did_augassign(slot))

    def scb_did_read_unreplacable(self, slot: ScbSlot) -> bool:
        return self.runs.scb_did_read_unreplacable(slot)

    def func_ref(self) -> Optional["MCFunctionFile"]:
        return self.runs.func_ref()

    def scb_replace(self, origin: ScbSlot, target: ScbSlot):
        subcmds = []
        for subcmd in self.subcmds:
            rep = subcmd.scb_replace(origin, target)
            if rep is None:
                subcmds.append(subcmd)
            else:
                subcmds.append(rep)
        runs = self.runs.scb_replace(origin, target)
        if runs is None:
            runs = self.runs
        return Execute(subcmds, runs)

class RawtextOutput(Command):
    def __init__(self, prefix: str, components: List[dict]):
        self.prefix = prefix
        self.score_components: List[dict] = []
        self.components = []
        for component in components:
            self.add_component(component)

    def add_component(self, component: dict):
        self.components.append(component)
        if "score" in component:
            d = component["score"]
            if "name" not in d or "objective" not in d:
                raise ValueError("Invalid score component: %r" % component)
            self.score_components.append(d)

    def resolve(self) -> str:
        return "%s %s" % (
            self.prefix, json.dumps({"rawtext": self.components})
        )

    def scb_did_read(self, slot: ScbSlot) -> bool:
        return any(
            slot.objective == d["objective"] and slot.target == d["name"]
            for d in self.score_components
        )

    def scb_replace(self, origin: ScbSlot, target: ScbSlot):
        components = deepcopy(self.components)
        for component in components:
            if "score" in component:
                d = component["score"]
                if "name" not in d or "objective" not in d:
                    raise ValueError
                if (origin.objective == d["objective"]
                    and origin.target == d["name"]):
                    d["name"] = target.target
                    d["objective"] = target.objective
        return RawtextOutput(self.prefix, components)

class TitlerawTimes(Command):
    def __init__(self, player: str, fade_in: int, stay: int, fade_out: int):
        self.player = player
        self.fade_in = fade_in
        self.stay = stay
        self.fade_out = fade_out

    def resolve(self) -> str:
        return "titleraw %s times %d %d %d" % (
            self.player, self.fade_in, self.stay, self.fade_out
        )

class TitlerawResetTimes(Command):
    def __init__(self, player: str):
        self.player = player

    def resolve(self) -> str:
        return "titleraw %s reset" % self.player

class TitlerawClear(Command):
    def __init__(self, player: str):
        self.player = player

    def resolve(self) -> str:
        return "titleraw %s clear" % self.player

class FunctionsManager:
    EXTRA_OBJ = "{scb}{id}"

    def __init__(self, init_file_path: str):
        self.files: List["MCFunctionFile"] = []
        self.init_file_path = init_file_path
        self.init_file: Optional["MCFunctionFile"] = None
        self._alloc_id = 0
        self._int_consts: Dict[int, ScbSlot] = {}
        self._scb_id = 0

    def generate_init_file(self):
        if self.init_file is not None:
            return
        self.init_file = res = MCFunctionFile(self.init_file_path)
        res.write_debug(
            '## Usage: Initialize Acacia, only need to be ran ONCE',
            '## Execute this before running anything from Acacia!!!'
        )
        # Default scoreboard
        res.write_debug('# Register scoreboard')
        res.write(ScbObjAdd(Config.scoreboard))
        # Constants
        if self._int_consts:
            res.write_debug('# Load constants')
            res.extend(
                ScbSetConst(slot, num)
                for num, slot in self._int_consts.items()
            )
        # Extra scoreboard
        if self._scb_id >= 1:
            res.write_debug('# Additional scoreboards')
            res.extend(
                ScbObjAdd(self.EXTRA_OBJ.format(scb=Config.scoreboard, id=i))
                for i in range(1, self._scb_id + 1)
            )
        self.add_file(res)

    def allocate(self) -> ScbSlot:
        self._alloc_id += 1
        return ScbSlot("acacia%d" % self._alloc_id, Config.scoreboard)

    def add_file(self, file: "MCFunctionFile"):
        self.files.append(file)

    def int_const(self, number: int) -> ScbSlot:
        if number not in self._int_consts:
            self._int_consts[number] = self.allocate()
        return self._int_consts[number]

    def add_scoreboard(self) -> str:
        self._scb_id += 1
        return self.EXTRA_OBJ.format(scb=Config.scoreboard, id=self._scb_id)