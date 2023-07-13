"""
music - Generate redstone music from MIDI file
NOTE Python package `mido` is required.
"""

from acaciamc.mccmdgen.expression import *
from acaciamc.mccmdgen.generator import MCFunctionFile
from acaciamc.ast import ModuleMeta
from acaciamc.error import ErrorType
from acaciamc.tools import axe, resultlib

class MusicType(Type):
    """
    Music(
        path: str,
        looping: bool-literal = False,
        loop_interval: int-literal = 50,
        execute_condition: str = "as @a at @s",
        note_offset: int-literal = 0,
        chunk_size: int-literal = 500,
        speed: float = 1.0,
        volume: float = 1.0
    )

    A music to generate from MIDI file `path`.
    If `looping` is True, the music will be played repeatingly, with
    interval `loop_interval` before replaying.
    `execute_condition` sets the subcommand of /execute used by
    /playsound. By setting this you can specify where the music is
    played and who would hear it.
    `note_offset` would make the whole music higher if it is positive,
    or lower if negative.
    Since music runs a LOT of commands every tick, we seperate commands
    into several files to make sure you are not running too many commands
    every tick. `chunk_size` determines how many commands there will be
    in 1 file.
    `speed` sets the speed of music.
    `volume` sets the volume factor of music.
    """
    name = "Music"

    def do_init(self):
        @axe.chop
        @axe.arg("path", axe.LiteralString())
        @axe.arg("looping", axe.LiteralBool(), default=False)
        @axe.arg("loop_interval", axe.LiteralInt(), default=50)
        @axe.arg("execute_condition", axe.LiteralString(),
                 default="as @a at @s")
        @axe.arg("note_offset", axe.LiteralInt(), default=0)
        @axe.arg("chunk_size", axe.LiteralInt(), default=500)
        @axe.arg("speed", axe.LiteralFloat(), default=1.0)
        @axe.arg("volume", axe.LiteralFloat(), default=1.0)
        def _new(compiler, path: str, looping: bool, loop_interval: int,
                 execute_condition: str, note_offset: int,
                 chunk_size: int, speed: float, volume: float):
            try:
                midi = mido.MidiFile(path)
            except Exception as err:
                raise Error(ErrorType.IO, message="MIDI parser: %s" % err)
            if chunk_size <= 0:
                raise axe.ArgumentError("chunk_size", "must be positive")
            if speed <= 0:
                raise axe.ArgumentError("speed", "must be positive")
            if volume <= 0:
                raise axe.ArgumentError("volume", "must be positive")
            looping_info = loop_interval if looping else -1
            return Music(
                midi, execute_condition, looping_info, note_offset,
                chunk_size, speed, volume, compiler
            )
        self.attribute_table.set(
            "__new__", BinaryFunction(_new, self.compiler)
        )

class Music(AcaciaExpr):
    # NOTE We are using `MT` to refer to 1 MIDI tick and `GT` for 1 MC game
    # tick.
    # CONFIGS
    ID2INSTRUMENT = {
        # Piano
        0: 'note.harp',
        1: 'note.harp',
        2: 'note.pling',
        3: 'note.pling',
        4: 'note.pling',
        5: 'note.pling',
        6: 'note.harp',
        7: 'note.pling',
        # Chromatic Percussion
        8: 'note.harp',
        9: 'note.bell',
        10: 'note.chime',
        11: 'note.iron_xylophone',
        12: 'note.xylophone',
        13: 'note.xylophone',
        14: 'note.chime',
        15: 'note.bell',
        # Organ
        # Organ sounds like flute somehow...
        16: 'note.flute',
        17: 'note.flute',
        18: 'note.flute',
        19: 'note.flute',
        20: 'note.flute',
        21: 'note.flute',
        22: 'note.flute',
        23: 'note.flute',
        # Guitar
        24: 'note.guitar',
        25: 'note.guitar',
        26: 'note.guitar',
        27: 'note.guitar',
        28: 'note.guitar',
        29: 'note.guitar',
        30: 'note.guitar',
        31: 'note.bass',
        # Bass
        32: 'note.bass',
        33: 'note.bass',
        34: 'note.bass',
        35: 'note.bass',
        36: 'note.bass',
        37: 'note.bass',
        38: 'note.bass',
        39: 'note.bass',
        # Solo String
        # Strings like violin sounds like flute somehow...
        40: 'note.flute',
        41: 'note.flute',
        42: 'note.flute',
        43: 'note.flute',
        44: 'note.guitar',
        45: 'note.guitar',
        46: 'note.harp',
        47: 'note.snare',
        # Ensemble
        48: 'note.flute',
        49: 'note.flute',
        50: 'note.flute',
        51: 'note.flute',
        52: 'note.flute',
        53: 'note.flute',
        # Brass
        54: 'note.flute',
        55: 'note.snare',
        56: 'note.chime',
        57: 'note.chime',
        58: 'note.chime',
        59: 'note.chime',
        60: 'note.chime',
        61: 'note.chime',
        62: 'note.chime',
        63: 'note.chime',
        # Reed
        # note.bit sounds like Sax somehow...
        64: 'note.bit',
        65: 'note.bit',
        66: 'note.bit',
        67: 'note.bit',
        68: 'note.flute',
        69: 'note.flute',
        70: 'note.flute',
        71: 'note.flute',
        # Pipe
        72: 'note.flute',
        73: 'note.flute',
        74: 'note.flute',
        75: 'note.flute',
        76: 'note.flute',
        77: 'note.flute',
        78: 'note.bell',
        79: 'note.flute',
        # Synth Lead
        80: 'note.bit',
        81: 'note.bit',
        82: 'note.flute',
        83: 'note.flute',
        84: 'note.guitar',
        85: 'note.bit',
        86: 'note.bit',
        87: 'note.bit',
        # Synth Pad
        88: 'note.bit',
        89: 'note.bit',
        90: 'note.bit',
        91: 'note.bit',
        92: 'note.guitar',
        93: 'note.bit',
        94: 'note.bit',
        95: 'note.guitar',
        # Synth Effect
        96: 'note.bit',
        97: 'note.bit',
        98: 'note.bit',
        99: 'note.bit',
        100: 'note.bit',
        101: 'note.bit',
        102: 'note.bit',
        103: 'note.bit',
        # Ethnic
        104: 'note.guitar',
        105: 'note.banjo',
        106: 'note.guitar',
        107: 'note.guitar',
        108: 'note.bell',
        109: 'note.flute',
        110: 'note.guitar',
        111: 'note.flute',
        # Percussive
        112: 'note.bell',
        113: 'note.bell',
        114: 'note.drum',
        115: 'note.cow_bell',
        116: 'note.drum',
        117: 'note.drum',
        118: 'note.drum',
        119: 'note.bit',
        # Sound Effects
        120: 'note.hat',
        121: 'note.hat',
        122: 'note.hat',
        123: 'note.hat',
        124: 'note.hat',
        125: 'note.hat',
        126: 'note.hat',
        127: 'note.snare'
    }
    CHANNEL_VOLUME = {
        i: 1.0 for i in range(16)
    }

    def __init__(self, midi, exec_condition: str, looping: int,
                 note_offset: int, chunk_size: int, speed: float,
                 volume: float, compiler):
        super().__init__(DataType.from_type_cls(MusicType, compiler), compiler)
        self.midi = midi
        self.execute_condition = exec_condition
        self.note_offset = note_offset
        self.chunk_size = chunk_size
        self.tracks = [t.copy() for t in midi.tracks]
        # Check MIDI type
        if midi.type != 0 and midi.type != 1:
            raise Error(ErrorType.ANY,
                        message="Unsupported MIDI type: %d" % midi.type)
        # Speed settings
        self.bpm = 120
        self.mt_per_beat = midi.ticks_per_beat
        self.user_speed = speed
        # Ticking
        self.mt = 0
        self.gt = 0.0
        self.gt_int = 0  # Always == round(self.gt)
        self.last_gt_int = 0
        # last_msg_mt: track id to MT when last Message is handled
        self.last_msg_mt = dict.fromkeys(range(len(midi.tracks)), 0)
        # Channel info
        self.channel_volume = {}  # channel id to volume (0-127)
        self.channel_instrument = {}  # channel id to instrument id
        ## Default instrument: 0~8 & 9~15: Piano (0); 9: Drum set (127)
        ## Default volumn: 100
        for i in range(16):
            self.channel_instrument[i] = 0
            self.channel_volume[i] = 100
        self.channel_instrument[9] = 127
        # Timer:
        #   when 0 <= timer <= music length, the music is playing
        #   when timer > music length, the music has ended
        #   when timer < 0, it's the countdown of starting playing
        self.timer = self.compiler.types[IntType].new_var()
        # Volume
        self.user_volume = volume
        # Create file
        self.files = []
        # file_sep_gt: in which GT we seperate the file
        self.file_sep_gt = []
        self.cur_chunk_size = 0  # Commands written in current file
        self.new_file()  # Initial file
        # Go
        while not self.is_finished():
            self.main_loop()
        GT_LEN = self.gt_int  # Length of music in GT
        # The last file may be useless
        if not self.files[-1].has_content():
            self.files.pop()
            self.file_sep_gt.pop()
        # Add file
        for file in self.files:
            self.compiler.add_file(file)
        self.file_sep_gt.append(GT_LEN + 1)
        # Create GT loop using `schedule` module
        @axe.chop
        def _gt_loop(compiler):
            cmds = []
            cmds.extend(
                export_execute_subcommands(
                    ["if score %s matches %d..%d" % (
                        self.timer,
                        self.file_sep_gt[i], self.file_sep_gt[i+1] - 1
                    )], main=file.call()
                )
                for i, file in enumerate(self.files)
            )
            cmds.extend(
                export_execute_subcommands(
                    ["if score %s matches ..%d" % (self.timer, GT_LEN)],
                    main=cmd
                )
                for cmd in self.timer.iadd(IntLiteral(1, self.compiler))
            )
            if looping >= 0:
                cmds.extend(export_execute_subcommands(
                    ["if score %s matches %d" % (self.timer, GT_LEN + 1)],
                    main=cmd
                ) for cmd in IntLiteral(-looping, compiler)
                             .export(self.timer))
            return resultlib.commands(cmds, compiler)
        # Register this to be called every tick
        _res, cmds = register_loop.call(
            args=(BinaryFunction(_gt_loop, self.compiler),),
            keywords={}
        )
        # Create attributes
        self.attribute_table.set("_timer", self.timer)
        self.attribute_table.set("LENGTH", IntLiteral(GT_LEN, self.compiler))
        @axe.chop
        def _init(compiler):
            """.__init__(): Register dependencies"""
            return resultlib.commands(cmds, compiler)
        self.attribute_table.set("__init__",
                                 BinaryFunction(_init, self.compiler))
        @axe.chop
        @axe.arg("timer", IntType, default=IntLiteral(0, self.compiler))
        def _play(compiler, timer: AcaciaExpr):
            """
            .play(timer: int = 0)

            Start playing the music. When `timer` < 0, its the delay
            of playing. When `timer` >= 0, its where the music starts
            playing.
            """
            cmds = timer.export(self.timer)
            return resultlib.commands(cmds, compiler)
        self.attribute_table.set("play", BinaryFunction(_play, self.compiler))
        @axe.chop
        def _stop(compiler):
            """.stop(): Stop the music"""
            cmds = IntLiteral(GT_LEN + 2, compiler).export(self.timer)
            return resultlib.commands(cmds, compiler)
        self.attribute_table.set("stop", BinaryFunction(_stop, self.compiler))

    def main_loop(self):
        # Read messages
        for i, track in enumerate(self.tracks):
            if not track:
                continue
            message = track[0]
            if message.time > self.mt - self.last_msg_mt[i]:
                continue
            # Handle message
            mtype = message.type
            if mtype == "note_on":
                if message.velocity != 0:
                    self.play_note(message)
            elif mtype == "set_tempo":
                self.bpm = 6E+7 / message.tempo
            elif message.is_cc():
                if message.control == 7:  # Volume
                    self.channel_volume[message.channel] = message.value
            elif mtype == "program_change":
                self.channel_instrument[message.channel] = message.program
            # Reset timer
            self.last_msg_mt[i] = self.mt
            track.pop(0)
        # Time increment
        self.mt += 1
        # bpm * mt_per_beat is MT per minute. Divide it by 1200 to get MT
        # per GT, and multiply it by `user_speed` at last
        self.gt += 1 / (self.bpm * self.mt_per_beat * self.user_speed / 1200)
        self.gt_int = round(self.gt)
        # Update last_gt_int
        if self.gt_int > self.last_gt_int:
            self.last_gt_int = self.gt_int
            # New file check
            if self.cur_chunk_size >= self.chunk_size:
                self.new_file()

    def new_file(self):
        self.cur_file = MCFunctionFile()
        self.files.append(self.cur_file)
        self.cur_file.write_debug("# Music loop")
        self.file_sep_gt.append(self.gt_int)
        self.cur_chunk_size = 0

    def is_finished(self):
        return not any(self.tracks)

    def get_instrument(self, channel: int) -> str:
        """Get MC sound of channel."""
        ins_id = self.channel_instrument[channel]
        return self.ID2INSTRUMENT[ins_id]

    def get_volume(self, channel: int, velocity: int) -> float:
        """Get MC volume (0~1) according to channel and velocity."""
        channel_v = (self.channel_volume[channel]
                     * self.CHANNEL_VOLUME[channel])
        return velocity * channel_v / 127 / 127 * self.user_volume

    def get_pitch(self, note: int) -> float:
        """Get MC pitch from MIDI note"""
        return 2 ** ((note + self.note_offset - 54) / 12 - 1)

    def play_note(self, message):
        """Play a note according to note_on Message"""
        volume = self.get_volume(message.channel, message.velocity)
        pitch = self.get_pitch(message.note)
        sound = self.get_instrument(message.channel)
        gt = self.gt_int
        self.cur_file.write(
            "execute if score %s matches %d %s run " %
            (self.timer, gt, self.execute_condition) +
            "playsound %s @s ~~~ %.2f %.3f" %
            (sound, volume, pitch)
        )
        self.cur_chunk_size += 1

@axe.chop
@axe.arg("id", axe.LiteralInt(), rename="id_")
@axe.arg("sound", axe.LiteralString())
def _set_instrument(compiler, id_: int, sound: str):
    """
    music.set_instrument(id: int-literal, sound: str):
        Set instrument mapping

    Set the sound of MIDI instrument `id` to Minecraft
    sound `sound`.
    Example:
        # Set MC sound of ID 127 instrument to `note.hat`
        music.set_instrument(127, "note.hat")
    """
    if id_ >= 128 or id_ < 0:
        raise axe.ArgumentError('id', 'must in 0~127')
    Music.ID2INSTRUMENT[id_] = sound
    return resultlib.nothing(compiler)

@axe.chop
@axe.arg("channel", axe.LiteralInt())
@axe.arg("volume", axe.LiteralFloat())
def _channel_volume(compiler, channel: int, volume: float):
    """
    music.channel_volume(channel: int-literal, volume: float)

    Modify volume of specified channel.
    """
    if channel >= 16 or channel < 0:
        raise axe.ArgumentError('channel', 'must in 0~15')
    if volume < 0:
        raise axe.ArgumentError('volume', "can't be negative")
    Music.CHANNEL_VOLUME[channel] = volume
    return resultlib.nothing(compiler)

def acacia_build(compiler):
    global mido, register_loop
    try:
        import mido
    except ImportError:
        raise Error(ErrorType.ANY,
                    message="Python module 'mido' is required")
    schedule = compiler.get_module(ModuleMeta("schedule"))
    register_loop = schedule.attribute_table.lookup("register_loop")
    compiler.add_type(MusicType)
    return {
        "Music": compiler.types[MusicType],
        "set_instrument": BinaryFunction(_set_instrument, compiler),
        "channel_volume": BinaryFunction(_channel_volume, compiler)
    }
