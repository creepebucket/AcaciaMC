# Acacia
English | [中文](README_cn.md)

## Introduction
**Acacia is a programming language that runs in Minecraft Bedrock Edition.**
Minecraft commands can be complicated, long and hard to maintain.
Acacia is an alternative to commands -- it is also used to control Minecraft.
*However*, Acacia code is much more readable than commands, which increases the maintainability of your project and your productivity.
**Imagine writing a Tetris game that runs in Minecraft using less than 14KB code** (see [below](#what-can-acacia-do))!

Acacia code is finally compiled into `.mcfunction` files.
In other word, Acacia code will be converted into Minecraft commands by the program, and can be loaded in a Minecraft world as a behavior pack.

Still confused? Here's a simple Acacia program that calculates sum of elements in an arithmetic sequence in Minecraft:
```
import print
def arithmetic(start: int, to: int, delta=1) -> int:
    #*
     * Return sum of arithmetic sequence that starts with `start`,
     * ends with `to` with common difference `delta`.
     *#
    result := (start + to) * ((to - start) / delta + 1) / 2
res := arithmetic(-30, 14, delta=2)
print.tell(print.format("Sum of arithmetic sequence (-30~14, d=2) is %0", res))
```
Acacia will convert the above code into commands:
```mcfunction
# These are AUTO-GENERATED! Isn't that cool?
scoreboard players set acacia1 acacia -30
scoreboard players set acacia2 acacia 14
scoreboard players set acacia3 acacia 2
scoreboard players operation acacia8 acacia = acacia2 acacia
scoreboard players operation acacia8 acacia -= acacia1 acacia
scoreboard players operation acacia8 acacia /= acacia3 acacia
scoreboard players add acacia8 acacia 1
scoreboard players operation acacia7 acacia = acacia8 acacia
scoreboard players operation acacia6 acacia = acacia1 acacia
scoreboard players operation acacia6 acacia += acacia2 acacia
scoreboard players operation acacia6 acacia *= acacia7 acacia
scoreboard players operation acacia6 acacia /= acacia5 acacia
scoreboard players operation acacia4 acacia = acacia6 acacia
scoreboard players operation acacia9 acacia = acacia4 acacia
tellraw @a {"rawtext": [{"text": "Sum of arithmetic sequence (-30~14, d=2) is "}, {"score": {"objective": "acacia", "name": "acacia9"}}]}
```
```mcfunction
# Initialization: add scoreboard and set constants.
scoreboard objectives add acacia dummy
scoreboard players set acacia5 acacia 2
```
Running these generated commands will send this message in Minecraft's chat:
> Sum of arithmetic sequence (-30~14, d=2) is -184

**In conclusion, by using Acacia you can create Minecraft projects -- not by writing commands, but by writing Acacia code, which is much more easier to maintain and understand.**

Acacia is written in Python, so Python (3.6 or newer) is required by compiler (i.e. the program that converts your code into commands).

## What can Acacia do?
Some real-world examples:
- **Without writing 1 command**, we can create a simple Tetris game in Minecraft!
  The source code can be found [here](test/demo/tetris.aca).
  It is only 14KB in size! The generated commands, however, use about 280KB and 50 files.
- Still without 1 command, a random Minecraft maze generator can be made using 3.5KB code
  (with comment that explains the algorithm removed). See [source code](test/demo/maze.aca).
- Noteblock musics can be automatically generated by the builtin module `music`.

Detailed features:
- No more redundant commands and huge amount of files; Acacia code is simple.
- No more worries about `/execute` context.
- No more entity tags; Acacia has an exclusive entity system!
- No more scoreboards! Instead we have the variable system which is popular in computer programming.
- No more repetitive commands; Acacia is good at generating repetitive commands.
- You can define loops and use the "if" statement to run something conditionally.
- Acacia provides various compile-time constants, including numbers, strings, arrays, maps and even world positions.
  This makes your map or addon more flexible.

Check out [this file](test/brief.aca) for more information about Acacia's syntax.

## Syntax Overview
This is how to define a variable in Acacia: `a := 1`. That's it.
No need for scoreboards.

Nested expressions within 1 line of code:
```python
a := 10
b := (10 + a) * a - 5
```

Function definitions:
```python
def foo(x: int, y = True) -> int:
    # Here is function body code
    result := x
    if y:
        result += 10
z: int
# These are all valid:
foo(1)
z = foo(2, False)
z = foo(x=3)
```

Flow control statements (selections and loops):
```python
def is_prime(x: int) -> bool:
    #* Test if `x` is a prime number *#
    result: bool = True
    mod: int = 2
    while mod <= x / 2:
        if x % mod == 0:
            result = False
        mod += 1
```

Various builtin modules:
```python
import print
money := 10
# Send "Hello, world!" in chat to everyone
print.tell("Hello world!")
# Show "Money: (Value of variable `money`)" on actionbar to everyone
print.title(print.format("Money: %0", money), mode=print.ACTIONBAR)
```
```python
import music
# Generate a noteblock music and use 1.2x speed.
m -> music.Music("music_score.mid", speed=1.2)
m.play()
```

Use of constants and `for` to avoid repetitive code:
```python
import world

# Place concretes of different colors according to value of an variable
COLORS -> {
    0: "cyan", 1: "orange", 2: "yellow",
    3: "purple", 4: "lime", 5: "red", 6: "blue"
}
i := 0  # Calculate `i`...
for c in COLORS:
    if c == i:
        world.setblock(
            Pos(0, -50, 0),
            world.Block("concrete", {"color": COLORS[c]})
        )
```

Position and entity system:
```python
import world

ORIGIN -> AbsPos(0, -50, 0)
world.fill(ORIGIN, Offset().offset(x=5, z=5), world.Block("air"))

entity Test:
    @type: "armor_stand"
    @position: ORIGIN

    def __init__():
        world.setblock(Pos(self), world.Block("diamond_block"))
        world.effect_give(self, "invisibility", duration=1000)

    def foo():
        world.tp(self, ORIGIN)

test_group: Engroup(Test)
test_group.select(Enfilter().distance_from(ORIGIN, max=5))
for test in test_group:
    test.foo()
```

## Discover More about Acacia
- [An introduction video in Chinese](https://www.bilibili.com/video/BV1uR4y167w9)
- [Use Acacia to generate noteblock musics](https://www.bilibili.com/video/BV1f24y1L7DB)
- Go to [this test file](test/brief.aca) for more details about Acacia!
- A simple Guess the Number game written in Acacia can also be found [here](test/demo/numguess.aca)!
