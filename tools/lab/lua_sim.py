"""Run the PS4 config Lua against real EE memory from a PCSX2 savestate (mocked emulator API),
then write the patched memory into another savestate slot so PCSX2 can run the exact result.

usage: python lua_sim.py <config.lua> <src_slot> <dst_slot> [vsyncs]
"""
import struct, sys
try:
    from lupa.lua51 import LuaRuntime      # closest to the emulator's Lua
except ImportError:
    from lupa import LuaRuntime
from statepatch import read_state, write_state, SS


def run(lua_path, src, dst, vsyncs=60):
    st = read_state(SS % src)
    mem = bytearray(st['eeMemory.bin'])
    writes = {}
    hooks, out, hooks_ee = [], [], []

    def r32(a):
        return struct.unpack_from('<i', mem, int(a) & 0x1FFFFFF)[0]   # signed, like the PS4 emulator

    def w32(a, v):
        a = int(a) & 0x1FFFFFF
        struct.pack_into('<I', mem, a, int(v) & 0xFFFFFFFF)
        writes[a] = int(v) & 0xFFFFFFFF

    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    ee = lua.table(ReadMem32=r32, WriteMem32=w32, AddHook=lambda pc, op, f: hooks_ee.append((int(pc), f)),
                   GetGpr=lambda r: 0, SetGpr=lambda r, v: None, GetPc=lambda: 0)
    emu = lua.table(AddVsyncHook=lambda f: hooks.append(f))
    g.getEEObject = lambda: ee
    g.getEmuObject = lambda: emu
    g.apiRequest = lambda v: None
    g.print = lambda *a: out.append(' '.join(str(x) for x in a))
    lua.execute(open(lua_path, encoding='utf-8').read())
    for _ in range(vsyncs):
        for h in hooks:
            h()
    for pc, f in hooks_ee:
        f()
    print(f'{len(hooks)} vsync hooks, {len(hooks_ee)} EE hooks, {len(writes)} words written')
    for line in out:
        print('  lua:', line)
    st['eeMemory.bin'] = bytes(mem)
    write_state(SS % dst, st)
    return writes


if __name__ == '__main__':
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 60)
