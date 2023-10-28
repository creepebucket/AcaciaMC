"""Command abstraction optimizer."""

__all__ = ["Optimizer"]

from typing import Iterable, Dict, Set, List, Tuple
from abc import ABCMeta, abstractmethod

import acaciamc.mccmdgen.cmds as cmds
from acaciamc.constants import Config

class Optimizer(cmds.FunctionsManager, metaclass=ABCMeta):
    def optimize(self):
        """Start optimizing."""
        self.opt_dead_functions()
        self.opt_tmp_variables()
        self.opt_function_inliner()

    def is_volatile(self, slot: cmds.ScbSlot) -> bool:
        """Can be implemented by subclasses to mark scores as volatile.
        By default, scores whose target is not a fake player are
        considered volatile.
        Scores that do not have unique representation (like selector)
        or might be referenced outside this command project should be
        set to volatile.
        """
        return slot.is_selector()

    @abstractmethod
    def entry_files(self) -> Iterable[cmds.MCFunctionFile]:
        """Must be implemented by subclasses to mark mcfunction files
        as an entry so that optimizer won't delete them even if they
        are not referenced.
        """
        pass

    def opt_dead_functions(self):
        """Remove unreferenced functions."""
        ref_map: Dict[cmds.MCFunctionFile, Set[cmds.MCFunctionFile]] = {}
        for file in self.files:
            refs = set(command.func_ref() for command in file.commands)
            if None in refs:
                refs.remove(None)
            ref_map[file] = refs
        visited = set()
        def _visit(file: cmds.MCFunctionFile):
            if file in visited:
                return
            visited.add(file)
            for ref in ref_map[file]:
                _visit(ref)
        for file in self.entry_files():
            _visit(file)
        self.files = list(visited)

    def opt_tmp_variables(self):
        """Remove unnecessary temporary variables generated by Acacia.
        e.g. x = 10 + x  (acacia1 acacia -> x)
            scoreboard players set acacia2 acacia 10
            scoreboard players operation acacia2 acacia += acacia1 acacia
            scoreboard players operation acacia3 acacia = acacia2 acacia
            scoreboard players operation acacia1 acacia = acacia3 acacia
        Unnecessary use of acacia3 can be removed.
        """
        for file in self.files:
            # Scan
            scopes: List[Tuple[cmds.ScbSlot, cmds.ScbSlot, int, int]] = []
            openings: Dict[cmds.ScbSlot, Tuple[cmds.ScbSlot, int]] = {}
            openings_const: Dict[cmds.ScbSlot, Tuple[int, int]] = {}
            for i, command in enumerate(file.commands):
                for origin, (target, _) in openings.copy().items():
                    if (command.scb_did_augassign(origin)
                        or command.scb_did_read_unreplacable(origin)
                        or command.scb_did_assign(target)
                        or command.scb_did_augassign(target)):
                        del openings[origin]
                        continue
                    if command.scb_did_assign(origin):
                        info = openings.pop(origin)
                        scopes.append((origin, *info, i))
                for origin in openings_const.copy():
                    if (command.scb_did_augassign(origin)
                        or command.scb_did_read_unreplacable(origin)):
                        del openings_const[origin]
                        continue
                    if command.scb_did_assign(origin):
                        number, begin_i = openings_const.pop(origin)
                        scopes.append(
                            (origin, self.int_const(number), begin_i, i)
                        )
                if (isinstance(command, cmds.ScbOperation)
                    and command.operator is cmds.ScbOp.ASSIGN):
                    origin, target = command.operand1, command.operand2
                    if (not self.is_volatile(origin)
                        and not self.is_volatile(target)):
                        openings[origin] = (target, i)
                elif isinstance(command, cmds.ScbSetConst):
                    origin = command.target
                    if not self.is_volatile(origin):
                        openings_const[origin] = (command.value, i)
            # Optimize
            # if scopes:
            #     print("Opt in", file.get_path())
            for origin, replace, start, end in scopes:
                # print("  %s -> %s, from %d to %d"
                #       % (origin, replace, start, end))
                for i, command in enumerate(file.commands[start+1 : end]):
                    rep = command.scb_replace(origin, replace)
                    if rep is not None:
                        file.commands[start + 1 + i] = rep
            for i in sorted((i for _, _, i, _ in scopes), reverse=True):
                del file.commands[i]

    @property
    @abstractmethod
    def max_inline_file_size(self) -> int:
        pass

    def dont_inline_execute_call(self, file: cmds.MCFunctionFile) -> bool:
        """When True is returned, `execute ... run function` in `file`
        will not be inlined by `opt_function_inliner`.
        """
        return False

    def opt_function_inliner(self):
        """Expand mcfunctions that only have 1 reference."""
        # Locating optimizable
        todo: Dict[cmds.MCFunctionFile, Tuple[cmds.MCFunctionFile, int]] = {}
        called: Set[cmds.MCFunctionFile] = set()
        for file in self.files:
            no_execute = self.dont_inline_execute_call(file)
            for i, command in enumerate(file.commands):
                callee = command.func_ref()
                if callee is None:
                    continue
                runs = command
                can_opt = True
                while isinstance(runs, cmds.Execute):
                    if can_opt:
                        # Attempt to find some reason why it cannot be
                        # optimized...
                        if no_execute:
                            can_opt = False
                        # Environment other than if/unless score may
                        # change during execution of commands, so we
                        # can't inline it.
                        for subcmd in runs.subcmds:
                            if not isinstance(
                                subcmd, (cmds.ExecuteScoreComp,
                                        cmds.ExecuteScoreMatch)
                            ):
                                can_opt = False
                                break
                    runs = runs.runs
                if callee in called:
                    # More than 1 references
                    if callee in todo:
                        del todo[callee]
                else:
                    # First reference
                    if isinstance(runs, cmds.InvokeFunction) and can_opt:
                        todo[callee] = (file, i)
                    called.add(callee)
        # Optimize
        # for callee, (caller, caller_index) in todo.items():
        #     print("Inlining %s, called by %s at %d" % (
        #         callee.get_path(), caller.get_path(), caller_index
        #     ))
        merged: Set[cmds.MCFunctionFile] = set()
        def _merge(caller: cmds.MCFunctionFile):
            if caller in merged:
                return
            merged.add(caller)
            tasks: List[Tuple[int, cmds.MCFunctionFile]] = []
            for callee, (caller_got, caller_index) in todo.items():
                if caller_got != caller:
                    continue
                _merge(callee)
                tasks.append((caller_index, callee))
            tasks.sort(key=lambda x: x[0], reverse=True)
            for index, callee in tasks:
                runs = caller.commands[index]
                if isinstance(runs, cmds.Execute):
                    # Prefixing every command in a long file with
                    # /execute condition can reduce performance,
                    # so we don't inline it.
                    if callee.cmd_length() > self.max_inline_file_size:
                        continue
                # print("Merging %s to %s:%d" % (
                #     callee.get_path(), caller.get_path(), index
                # ))
                subcmds = []
                need_tmp = False
                while isinstance(runs, cmds.Execute):
                    subcmds.extend(runs.subcmds)
                    if not need_tmp:
                        for subcmd in runs.subcmds:
                            slots = []
                            if isinstance(subcmd, cmds.ExecuteScoreComp):
                                slots.append(subcmd.operand1)
                                slots.append(subcmd.operand2)
                            elif isinstance(subcmd, cmds.ExecuteScoreMatch):
                                slots.append(subcmd.operand)
                            else:
                                raise ValueError
                            for command in callee.commands:
                                for slot in slots:
                                    if (command.scb_did_assign(slot)
                                        or command.scb_did_augassign(slot)):
                                        need_tmp = True
                                        break
                    runs = runs.runs
                inserts = []
                if need_tmp:
                    tmp = self.allocate()
                    inserts.append(cmds.ScbSetConst(tmp, 0))
                    inserts.append(cmds.Execute(
                        subcmds, cmds.ScbSetConst(tmp, 1)
                    ))
                    for command in callee.commands:
                        inserts.append(cmds.execute(
                            [cmds.ExecuteScoreMatch(tmp, "1")], command
                        ))
                elif subcmds:
                    for command in callee.commands:
                        inserts.append(cmds.execute(subcmds, command))
                else:
                    inserts.extend(callee.commands)
                if Config.debug_comments:
                    fp = callee.get_path()
                    inserts.insert(0, cmds.Comment(
                        "## Function call to %s inlined by optimizer" % fp
                    ))
                    inserts.append(cmds.Comment("## Inline of %s ended" % fp))
                caller.commands[index : index+1] = inserts
                self.files.remove(callee)
        for caller, _ in todo.values():
            if caller not in todo:
                _merge(caller)
