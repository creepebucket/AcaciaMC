"""print - String formatting and printing module."""

from typing import List, Optional, Tuple, TYPE_CHECKING
from copy import deepcopy

from acaciamc.objects import *
from acaciamc.mccmdgen.expr import *
from acaciamc.mccmdgen.datatype import DefaultDataType
from acaciamc.mccmdgen.ctexpr import CTDataType
from acaciamc.mccmdgen.utils import unreachable
from acaciamc.error import *
from acaciamc.tools import axe, resultlib
from acaciamc.constants import COLORS, COLORS_NEW
import acaciamc.mccmdgen.cmds as cmds
import acaciamc.localization
from acaciamc.localization import get_text

lang = acaciamc.localization.get_lang()

def localize(text):
    return get_text(text, lang)
if TYPE_CHECKING:
    from acaciamc.compiler import Compiler
    from acaciamc.mccmdgen.mcselector import MCSelector

class ArgFString(axe.Multityped):
    """Accepts an fstring as argument. A string is also accepted and
    converted to an fstring.
    """
    def __init__(self):
        super().__init__((StringDataType, FStringDataType))

    def convert(self, origin: AcaciaExpr) -> "FString":
        origin = super().convert(origin)
        if isinstance(origin, String):
            fstr = FString([], [{"text": origin.value}])
        else:
            assert isinstance(origin, FString)
            fstr = origin
        return fstr

class _FStrError(Exception):
    def __str__(self):
        return self.args[0]

class _FStrParser:
    def __init__(self, pattern: str, args, keywords, compiler: "Compiler"):
        """Parse an fstring with `pattern` and `args` and `keywords`
        as formatted expressions."""
        self.pattern = pattern
        self.ptr = 0
        self.args = args
        self.keywords = keywords
        self.compiler = compiler
        self.dependencies = []
        self.json = []  # the result
        self.text_cache: List[str] = []

    def next_char(self) -> Optional[str]:
        """Move to next char."""
        if self.ptr >= len(self.pattern):
            return None
        c = self.pattern[self.ptr]
        self.ptr += 1
        return c

    def _dump_text(self):
        if self.text_cache:
            self.json.append({"text": "".join(self.text_cache)})
            self.text_cache.clear()

    def add_text(self, text: str):
        self.text_cache.append(text)

    def add_score(self, slot: cmds.ScbSlot):
        self._dump_text()
        self.json.append({
            "score": {"objective": slot.objective, "name": slot.target}
        })

    def add_expr(self, expr: AcaciaExpr):
        """Format an expression to string."""
        self._dump_text()
        if expr.data_type.matches_cls(IntDataType):
            if isinstance(expr, IntLiteral):
                # optimize for literals
                self.add_text(str(expr.value))
            else:
                dependencies, var = to_IntVar(expr, self.compiler)
                self.dependencies.extend(dependencies)
                self.add_score(var.slot)
        elif expr.data_type.matches_cls(BoolDataType):
            if isinstance(expr, BoolLiteral):
                # optimize for literals
                self.add_text('1' if expr.value else '0')
            else:
                dependencies, var = to_BoolVar(expr, self.compiler)
                self.dependencies.extend(dependencies)
                self.add_score(var.slot)
        elif isinstance(expr, String):
            self.add_text(expr.value)
        elif isinstance(expr, FString):
            self.json.extend(expr.json)
            self.dependencies.extend(expr.dependencies)
        else:
            raise _FStrError(localize("modules.print.fsrterror.addaxpr.error")% expr.data_type)

    def expr_from_id(self, name: str) -> AcaciaExpr:
        """Get the expr from an format
        e.g. "0" -> args[0]; "key" -> keywords["key"]
        """
        if name.isdecimal():
            index = int(name)
            try:
                expr = self.args[index]
            except IndexError:
                raise _FStrError(localize("modules.print.fsrterror.exprfromid.outofrange") % index)
        elif name in self.keywords:
            expr = self.keywords[name]
        else:
            raise _FStrError(localize('modules.print.fsrterror.exprfromid.invalid') % name)
        return expr

    def parse(self):
        char = ''
        while True:
            char = self.next_char()
            if char is None:
                break
            # Normal char
            if char != '%':
                self.add_text(char)
                continue
            # % format
            second = self.next_char()
            if second == '%' or second is None:
                # '%%' escape -> '%' OR '%' at the end of string
                self.add_text('%')
                continue
            # 1. Parse which expression is being used here
            if second == '{':
                # read until }
                expr_str = []
                expr_char = self.next_char()
                while expr_char != '}':
                    if expr_char is None:
                        raise _FStrError(localize("modules.print.fsrterror.parse.unclosedfstring"))
                    expr_str.append(expr_char)
                    expr_char = self.next_char()
                # expr is integer or an identifier
                expr = self.expr_from_id(''.join(expr_str))
            elif second.isdecimal():
                # %1 is the alias to %{1}
                expr = self.expr_from_id(second)
            else:
                # can't be understood, just use raw text
                self.add_text(char + second)
                continue
            # 3. Handle the `expr` we got
            self.add_expr(expr)
        self._dump_text()
        return self.dependencies, self.json

class FStringDataType(DefaultDataType):
    name = 'fstring'

ctdt_fstring = CTDataType("fstring")

class FString(ConstExprCombined):
    """A formatted string in JSON format."""
    cdata_type = ctdt_fstring

    def __init__(self, dependencies: List[str], json: List[dict]):
        # dependencies: commands to run before json rawtext is used
        # json: JSON rawtext without {"rawtext": ...}
        super().__init__(FStringDataType())
        self.dependencies = dependencies
        self.json = json

    def copy(self):
        return FString(self.dependencies.copy(), deepcopy(self.json))

    def cadd(self, other):
        # connect strings
        res = self.copy()
        if isinstance(other, String):
            res.json.append({"text": other.value})
        elif isinstance(other, FString):
            # connect json
            res.json.extend(other.json)
        else:
            unreachable()
        return res

    cradd = cadd

### Functions ###

## For creating strings

@axe.chop
@axe.arg("_pattern", axe.LiteralString(), rename="pattern")
@axe.star_arg("args", axe.AnyRT())
@axe.kwds("kwds", axe.AnyRT())
def _format(compiler, pattern: str, args, kwds):
    """
    format(_pattern: str, *args, **kwargs)

    Formatted string type.
    So far, `args` and `kwargs` may be int, bool, str and fstring
    NOTE Booleans are formatted as "0" and "1".
    in _pattern:
     "%%" -> character "%"
     "%{" integer "}" -> args[integer]
     "%" one-digit-number -> alias to `"%{" one-digit-number "}"`
     "%{" id "}" -> kwargs[id] (id is an valid Acacia identifier)
    Examples:
     format("Val1: %0; Val2: %{value}; Name: %{1}", val1, x, value=val2)
    """
    try:
        dependencies, json = _FStrParser(pattern, args, kwds, compiler).parse()
    except _FStrError as err:
        raise Error(ErrorType.ANY, message=str(err))
    # scan pattern
    return FString(dependencies, json)

@axe.chop
@axe.arg("key", axe.LiteralString())
def _translate(compiler, key: str):
    """
    Return an fstring that uses the given localization key.
    Example: format("Give me %0!", translate("item.diamond.name"))
    """
    return FString([], [{"translate": key}])

class _FontComponent(dict):
    def __init__(self, text: str, label: str):
        super().__init__()
        self["text"] = text
        self.label = label

COLOR_DEFAULT = "default"

@axe.chop
@axe.arg("text", ArgFString())
@axe.arg("color", axe.LiteralStringEnum(*COLORS, *COLORS_NEW, COLOR_DEFAULT),
         default=COLOR_DEFAULT)
@axe.arg("bold", axe.LiteralBool(), default=False)
@axe.arg("italic", axe.LiteralBool(), default=False)
@axe.arg("obfuscated", axe.LiteralBool(), default=False)
def _with_font(compiler: "Compiler", text: FString, color: str,
               bold: bool, italic: bool, obfuscated: bool):
    """
    with_font(
        text: str | fstring,
        color: str = "default",
        bold: bool-literal = False,
        italic: bool-literal = False,
        obfuscated: bool-literal = False
    ) -> fstring
    Return an fstring that has the given color and font when displayed.
    When uses of this function are embedded, for example:
        with_font(
            format("Hello %0!", with_font("world", "red", bold=True)),
            color="green"
        )
    The inner `with_font` has higher priority, so the result is:
        "Hello " (green) + "world" (red, bold) + "!" (green)
    When this function is used, it is not recommended to use formatting
    code (\u00A7, section sign; \# escape in Acacia) manually.
    """
    if color in COLORS_NEW and compiler.cfg.mc_version < (1, 19, 80):
        raise axe.ArgumentError(
            "color", localize("modules.print.withfont.onlyhighversion") % color
        )
    res = text.copy()
    fmts = []
    if color != COLOR_DEFAULT:
        if color in COLORS_NEW:
            color_str = COLORS_NEW[color]
        else:
            color_str = COLORS[color]
        fmts.append("\xA7" + color_str)
    if bold:
        fmts.append("\xA7l")
    if italic:
        fmts.append("\xA7o")
    if obfuscated:
        fmts.append("\xA7k")
    scopes: List[Tuple[int, int]] = []  # [start, end)
    start_i = 0
    start_levels = 0
    json_len = len(res.json)
    for i, component in enumerate(res.json):
        if isinstance(component, _FontComponent):
            if component.label == "start":
                start_levels += 1
                if start_levels == 1 and i > start_i:
                    scopes.append((start_i, i))
                    start_i = -1
            if component.label == "end":
                start_levels -= 1
                if start_levels == 0 and i != json_len - 1:
                    start_i = i + 1
    if start_levels:
        raise ValueError(localize("modules.print.withfont.unclosedfont"))
    if start_i != -1:
        scopes.append((start_i, json_len))
    scopes.reverse()
    fmt_code = "".join(fmts)
    for start_i, end_i in scopes:
        res.json.insert(end_i, _FontComponent("\xA7r", "end"))
        res.json.insert(start_i, _FontComponent(fmt_code, "start"))
    return res

## For printing

@axe.chop
@axe.arg("text", ArgFString())
@axe.arg("target", axe.PlayerSelector(), default=None)
def _tell(compiler, text: FString, target: Optional["MCSelector"]):
    """tell(text: str | fstring, target: PlayerSelector = <All players>)
    Tell the `target` the `text` using /tellraw.
    """
    commands = []
    if target is None:
        target_str = "@a"
    else:
        target_str = target.to_str()
    commands.extend(text.dependencies)
    commands.append(cmds.RawtextOutput("tellraw %s" % target_str, text.json))
    return resultlib.commands(commands)

# Title modes
_TITLE = 'title'
_SUBTITLE = 'subtitle'
_ACTIONBAR = 'actionbar'
# Default configurations
_FADE_IN = 10
_STAY_TIME = 70
_FADE_OUT = 20
_DEF_TITLE_CONFIG = (_FADE_IN, _STAY_TIME, _FADE_OUT)

@axe.chop
@axe.arg("text", ArgFString())
@axe.arg("target", axe.PlayerSelector(), default=None)
@axe.arg("mode", axe.LiteralStringEnum(_TITLE, _SUBTITLE, _ACTIONBAR),
         default=_TITLE)
@axe.arg("fade_in", axe.LiteralInt(), default=_FADE_IN)
@axe.arg("stay_time", axe.LiteralInt(), default=_STAY_TIME)
@axe.arg("fade_out", axe.LiteralInt(), default=_FADE_OUT)
def _title(compiler, text: FString, target: Optional["MCSelector"], mode: str,
           fade_in: int, stay_time: int, fade_out: int):
    """title(
        text: str | fstring,
        target: PlayerSelector = <All players>,
        mode: str = TITLE,
        fade_in: int-literal = 10,
        stay_time: int-literal = 70,
        fade_out: int-literal = 20
    )
    Use /titleraw for showing `text`.
    `fade_in`, `stay_time` and `fade_out` are in ticks.
    """
    commands = []
    if target is None:
        target_str = "@a"
    else:
        target_str = target.to_str()
    # Start
    ## set config
    conf = (fade_in, stay_time, fade_out)
    if conf != _DEF_TITLE_CONFIG:
        # only set config when it's not the default one
        commands.append(cmds.TitlerawTimes(target_str, *conf))
    ## titleraw
    commands.extend(text.dependencies)
    commands.append(
        cmds.RawtextOutput('titleraw %s %s' % (target_str, mode), text.json)
    )
    ## reset config
    if conf != _DEF_TITLE_CONFIG:
        # only reset when config is not the default one
        commands.append(cmds.TitlerawResetTimes(target_str))
    ## return
    return resultlib.commands(commands)

@axe.chop
@axe.arg("target", axe.PlayerSelector(), default=None)
def _title_clear(compiler, target: Optional["MCSelector"]):
    """title_clear(target: PlayerSelector = <All players>)
    Clear `target`'s title text.
    """
    if target is None:
        target_str = "@a"
    else:
        target_str = target.to_str()
    return resultlib.commands([cmds.TitlerawClear(target_str)])

def acacia_build(compiler: "Compiler"):
    return {
        'format': BinaryCTFunction(_format),
        'translate': BinaryCTFunction(_translate),
        'with_font': BinaryCTFunction(_with_font),
        'tell': BinaryFunction(_tell),
        'title': BinaryFunction(_title),
        'TITLE': String(_TITLE),
        'SUBTITLE': String(_SUBTITLE),
        'ACTIONBAR': String(_ACTIONBAR),
        'title_clear': BinaryFunction(_title_clear)
    }
