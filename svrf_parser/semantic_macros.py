"""Static macro signatures and branch-compatible recursion checks."""

from graphlib import CycleError, TopologicalSorter

from .symbol_availability import Availability, guarded_availability


def _compatible(left, right):
    return all((key, not value) not in right for key, value in left)


def enable_fmacro(validator, node, path):
    if any(_compatible(path, other) for other in validator.fmacro_enable_paths):
        validator.error("semantic.preprocessor.duplicate_using", "#USING KEYWORD FMACRO may only appear once", node)
    validator.fmacro_enable_paths.append(path)


def check_fmacro_enablement(validator):
    for node, path in validator.fmacro_calls:
        if guarded_availability(validator.fmacro_enable_paths, path) != Availability.DEFINITE:
            validator.warning("semantic.macro.fmacro_not_enabled", "FMACRO requires #USING KEYWORD FMACRO", node)


def check_macro_call(validator, name, node, scope, device):
    table = validator.symbol_table
    choices = [(guard, macro) for guard, macro in table.macro_definitions.get(name.upper(), ())
               if _compatible(guard, scope.branch_path)]
    if not choices:
        return
    count = len(node.cmacro_args if device else node.arguments)
    counts = {len(macro.params) for _, macro in choices}
    # A DEVICE call is embedded in a larger statement. Trailing layer operands
    # may belong to the DEVICE after textual substitution, not to the macro.
    if count not in counts and (not device or count < min(counts)):
        expected = " or ".join(str(n) for n in sorted(counts))
        validator.error("semantic.macro.argument_count", f"{name} expects {expected} argument(s), got {count}", node,
                        metadata={"expected_counts": sorted(counts), "actual_count": count})
    elif not device and len(counts) > 1 and count in counts:
        validator.warning("semantic.macro.conditional_argument_count",
                          f"The {count} supplied argument(s) do not fit every reachable definition of {name}", node)
    if scope.macro_owner is not None:
        edges = validator.macro_calls.setdefault(scope.macro_owner, [])
        edges.extend((macro, node, guard | scope.branch_path) for guard, macro in choices)


def check_macro_cycles(validator):
    edges = validator.macro_calls
    if not edges:
        return
    # Discard acyclic dependencies once. Only explore guard combinations in the
    # remaining subgraph, where a return to the calling definition is possible.
    sorter = TopologicalSorter({src: {dst for dst, _, _ in calls} for src, calls in edges.items()})
    try:
        sorter.prepare()
        return
    except CycleError:
        pass
    candidates = set(edges)
    while ready := sorter.get_ready():
        candidates.difference_update(ready)
        sorter.done(*ready)
    for owner in edges:
        if owner not in candidates:
            continue
        for dest, call, conditions in edges[owner]:
            pending = [(dest, conditions)]
            seen = set()
            while pending:
                current, path = pending.pop()
                if current is owner:
                    validator.error("semantic.macro.recursive", f"Recursive expansion of DMACRO {owner.name}", call)
                    break
                if current not in candidates or (current, path) in seen:
                    continue
                seen.add((current, path))
                pending.extend((target, path | guard) for target, _, guard in edges[current]
                               if _compatible(guard, path))
