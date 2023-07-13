"""print - String formatting and printing module."""

from typing import List
from copy import deepcopy
import json

from acaciamc.mccmdgen.expression import *
from acaciamc.error import *
from acaciamc.tools import axe, resultlib

class ArgFString(axe.Multityped):
    """Accepts an fstring as argument. A string is also accepted and
    converted to an fstring.
    """
    def __init__(self):
        super().__init__((StringType, FStringType))

    def convert(self, origin: AcaciaExpr) -> "FString":
        origin = super().convert(origin)
        if isinstance(origin, String):
            fstr = FString([], [], origin.compiler)
            fstr.add_text(origin.value)
        else:
            assert isinstance(origin, FString)
            fstr = origin
        return fstr

class _FStrError(Exception):
    def __str__(self):
        return self.args[0]

class _FStrParser:
    def __init__(self, pattern: str, args, keywords):
        """Parse an fstring with `pattern` and `args` and `keywords`
        as formatted expressions."""
        self.pattern = pattern
        self.args = args
        self.keywords = keywords
        self.dependencies = []
        self.json = []  # the result

    def next_char(self) -> str:
        """Move to next char."""
        if not self.pattern:
            return None
        ret = self.pattern[0]
        self.pattern = self.pattern[1:]
        return ret

    def add_text(self, text: str):
        # if the last component in json is text, too,
        # we add these text to it
        if bool(self.json) and self.json[-1].get('text'):
            self.json[-1]['text'] += text
        else:  # fallback
            self.json.append({"text": text})

    def add_score(self, objective: str, selector: str):
        self.json.append({
            "score": {"objective": objective, "name": selector}
        })

    def add_localization(self, key: str):
        self.json.append({"translate": key})

    def add_expr(self, expr: AcaciaExpr):
        """Format an expression to string."""
        if expr.data_type.raw_matches(IntType):
            if isinstance(expr, IntLiteral):
                # optimize for literals
                self.add_text(str(expr.value))
            else:
                dependencies, var = to_IntVar(expr)
                self.dependencies.extend(dependencies)
                self.add_score(var.objective, var.selector)
        elif expr.data_type.raw_matches(BoolType):
            if isinstance(expr, BoolLiteral):
                # optimize for literals
                self.add_text('1' if expr.value else '0')
            else:
                dependencies, var = to_BoolVar(expr)
                self.dependencies.extend(dependencies)
                self.add_score(var.objective, var.selector)
        elif isinstance(expr, String):
            self.add_text(expr.value)
        elif isinstance(expr, FString):
            self.json.extend(expr.json)
        else:
            raise _FStrError('Type "%s" can not be formatted as a string'
                             % expr.data_type)

    def expr_from_id(self, name: str) -> AcaciaExpr:
        """Get the expr from an format
        e.g. "0" -> args[0]; "key" -> keywords["key"]
        """
        if name.isdecimal():
            index = int(name)
            try:
                expr = self.args[index]
            except IndexError:
                raise _FStrError('Format index out of range: %d' % index)
        elif name in self.keywords:
            expr = self.keywords[name]
        else:
            raise _FStrError('Invalid format expression: %r' % name)
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
            # 1. After '%' can be a character indicating the mode
            if second == 'k':  # Valid mode
                mode = second
                third = self.next_char()
                if third is None:
                    self.add_text(char + mode)
                    continue
            else:  # No mode specified
                mode = ''
                third = second
            # 2. Parse which expression is being used here
            if third == '{':
                # read until }
                expr_str = ''
                expr_char = self.next_char()
                while expr_char != '}':
                    if expr_char is None:
                        raise _FStrError('Unclosed "{" in fstring')
                    expr_str += expr_char
                    expr_char = self.next_char()
                # expr is integer or an identifier
                expr = self.expr_from_id(expr_str)
            elif third.isdecimal():
                # %1 is the alia to %{1}
                expr = self.expr_from_id(third)
            else:
                # can't be understood, just use raw text
                self.add_text(char + mode + third)
                continue
            # 3. Handle the `expr` we got
            if mode == 'k':  # localization
                # An original `str` (not fstring) is required for
                # localization key
                if not isinstance(expr, String):
                    raise _FStrError(
                        'Type "%s" is not supported as localization key'
                        % expr.data_type)
                self.add_localization(expr.value)
            else:  # default mode
                self.add_expr(expr)
        return self.dependencies, self.json

class FStringType(Type):
    """
    format(_pattern: str, *args, **kwargs)

    Formatted string type.
    So far, `args` and `kwargs` may be int, bool, str and fstring
    NOTE Booleans are formatted as "0" and "1".
    in _pattern:
     "%%" -> character "%"
     "%{" integer "}" -> args[integer]
     "%" one-digit-number -> alia to `"%{" one-digit-number "}"`
     "%{" id "}" -> kwargs[id] (id is an valid Acacia identifier)
    Additionally, you can add following character after the first "%":
     "k": Use localization key
     (omitted): Default mode, format the expression as string
    Examples:
     format("Val1: %0; Val2: %{name}; Name: %{1}", val1, val2, name=x)
     format("Find %k{diamond} please!", diamond="item.diamond.name")
    """
    name = 'fstring'

    def do_init(self):
        @axe.chop
        @axe.arg("_pattern", axe.LiteralString(), rename="pattern")
        @axe.star_arg("args", axe.AnyValue())
        @axe.kwds("kwds", axe.AnyValue())
        def _new(compiler, pattern: str, args, kwds):
            try:
                dependencies, json = _FStrParser(pattern, args, kwds).parse()
            except _FStrError as err:
                raise Error(ErrorType.ANY, message=str(err))
            # scan pattern
            return FString(dependencies, json, compiler)
        self.attribute_table.set(
            '__new__', BinaryFunction(_new, self.compiler)
        )

class FString(AcaciaExpr):
    """A formatted string in JSON format."""
    def __init__(self, dependencies: List[str], json: list, compiler):
        # dependencies: commands to run before json rawtext is used
        # json: JSON rawtext without {"rawtext": ...}
        super().__init__(
            DataType.from_type_cls(FStringType, compiler), compiler
        )
        self.dependencies = dependencies
        self.json = json

    def export_json_str(self) -> str:
        return json.dumps({"rawtext": self.json})

    def add_text(self, text: str):
        # add text to fstring
        if bool(self.json) and self.json[-1].get('text'):
            self.json[-1]['text'] += text
        else:  # fallback
            self.json.append({"text": text})

    def deepcopy(self):
        return FString(
            deepcopy(self.dependencies), deepcopy(self.json), self.compiler
        )

    def __add__(self, other):
        # connect strings
        res = self.deepcopy()
        if isinstance(other, String):
            res.add_text(other.value)
        elif isinstance(other, FString):
            # connect json
            res.json.extend(other.json)
        else:
            return NotImplemented
        return res

    def __radd__(self, other):
        return self.__add__(other)

# output functions

@axe.chop
@axe.arg("text", ArgFString())
@axe.arg("target", axe.LiteralString(), default="@a")
def _tell(compiler, text: FString, target: str):
    """tell(text: str | fstring, target: str = "@a")
    Tell the `target` the `text` using /tellraw.
    """
    cmds = []
    # Convert str to fstring
    if isinstance(text, String):
        text, _cmds = compiler.types[FStringType].call(
            args=[text], keywords={}
        )
        cmds.extend(_cmds)
    cmds.extend(text.dependencies)
    cmds.append('tellraw %s %s' % (target, text.export_json_str()))
    return resultlib.commands(cmds, compiler)

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
@axe.arg("target", axe.LiteralString(), default="@a")
@axe.arg("mode", axe.LiteralString(), default=_TITLE)
@axe.arg("fade_in", axe.LiteralInt(), default=_FADE_IN)
@axe.arg("stay_time", axe.LiteralInt(), default=_STAY_TIME)
@axe.arg("fade_out", axe.LiteralInt(), default=_FADE_OUT)
def _title(compiler, text: FString, target: str, mode: str,
           fade_in: int, stay_time: int, fade_out: int):
    """title(
        text: str | fstring,
        target: str = "@a",
        mode: str = TITLE,
        fade_in: int-literal = 10,
        stay_time: int-literal = 70,
        fade_out: int-literal = 20
    )
    Use /titleraw for showing `text`.
    `fade_in`, `stay_time` and `fade_out` are in ticks.
    """
    cmds = []
    # Check valid mode
    if mode not in (_TITLE, _SUBTITLE, _ACTIONBAR):
        raise axe.ArgumentError('mode', 'invalid mode: %s' % mode)
    # Start
    ## set config
    conf = (fade_in, stay_time, fade_out)
    if conf != _DEF_TITLE_CONFIG:
        # only set config when it's not the default one
        cmds.append('titleraw %s times %d %d %d' % ((target,) + conf))
    ## titleraw
    cmds.extend(text.dependencies)
    cmds.append('titleraw %s %s %s' % (
        target, mode, text.export_json_str()
    ))
    ## reset config
    if conf != _DEF_TITLE_CONFIG:
        # only reset when config is not the default one
        cmds.append('titleraw %s reset' % target)
    ## return
    return resultlib.commands(cmds, compiler)

@axe.chop
@axe.arg("target", axe.LiteralString(), default="@a")
def _title_clear(compiler, target: str):
    """title_clear(target: str = "@a")
    Clear `target`'s title text.
    """
    return resultlib.commands(['titleraw %s clear' % target], compiler)

def acacia_build(compiler):
    compiler.add_type(FStringType)
    return {
        'format': compiler.types[FStringType],
        'tell': BinaryFunction(_tell, compiler),
        'title': BinaryFunction(_title, compiler),
        'TITLE': String(_TITLE, compiler),
        'SUBTITLE': String(_SUBTITLE, compiler),
        'ACTIONBAR': String(_ACTIONBAR, compiler),
        'title_clear': BinaryFunction(_title_clear, compiler)
    }
