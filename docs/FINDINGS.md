# Findings: Ratchet: Deadlocked on the PS4 PS2-Classics emulator

Tested on PS4 fw 13.52 with GoldHEN, emulator donors Rogue Galaxy v1 (revoke 270, `olympack` branch), War of the Monsters (2015),
JAK / Jak & Daxter (`titles/Jak1-TPL`, 2017, revoke 270).

## 1. The twisted skeleton and the explosion crashes: VU clamping

- The commonly shared config enables `--vu0/vu1/cop2-no-clamping=0` + `--*-clamp-results=1`. With that, Ratchet's model is twisted,
  and hitting or blowing up an enemy crashes the emulator (EE PC `0x6340EC`, `sw → D1_CHCR`, a VIF1 DMA start; the emulator then
  reads scratchpad memory far past its 16 KB end) or hangs the game.
- Found by elimination: switch everything off (fast, unsafe maths), then bring settings back one at a time:
  - all clamping off + `cop2-opt-flags=2` → model correct, but Ratchet is stuck "falling" (collision fails);
  - `+ cop2-accurate-mul=1` → still falling, model correct;
  - `+ FPU clamping` → still falling;
  - `+ cop2-opt-flags=0` → **walks, model correct, explosions fine**.
- Final: VU0/VU1/COP2 clamping OFF, FPU clamping ON, `cop2-opt-flags=0`, `cop2-accurate-mul=1`.
- The JAK emulator computes VU0 differently: with any of these settings the model is still broken there.

## 2. Multiplayer crash: our own skinning guard

- MP crashed with EE PC `0x0BFC0000` / `0x800002F8` right after the skinning-store guard was applied to the MP code (`0x4F9D20`).
- The guard's stubs lived at `0xFFD00`/`0xFFD40`, right next to the game's stack (~`0xFFD60`). Multiplayer uses more stack and
  overwrote them. Moving the stubs to `0x1FF0000` (a region that never holds data) fixed it.
- On the old War of the Monsters emulator MP starts without the guard but the geometry is broken (headless / invisible player).

## 3. Open: loading a save made at Dreadzone Station hangs

- Saves made elsewhere load. Reaching the station through normal play works. Loading a station save hangs on the loading screen,
  on both US and EU.
- The level LZ decompressor (`0x583A48`; toSPR DMA in 8 KB chunks, start `0x583C70`, wait `0x583C90`) finishes normally.
  The loader then follows the same path as a working load (`0x5BA3F0 → 0x57CA28 → 0x583FC0 → 0x578258 → 0x653560`, then `0x578258`
  called from `0x3CB578`), after which the EE stops completely (even vsync hooks stop).
- Not fixed by: an empty config (emulator defaults), Scalerize only, the IOP at full speed, the old config, removing the guard,
  or bounding the Scalerize signature scan.
- Next step: reproduce in PCSX2 and find what the loader waits for at that point (IOP / SIF RPC / CDVD / semaphore).

## Debugging tips for this emulator

- `--path-patches` can point to `/data/...`, so the Lua and config can be edited over FTP without reinstalling.
- `--ee-pc-coherency=1` puts the exact EE PC into crash dumps (klog on port 3232 with GoldHEN).
- Lua: `eeObj.ReadMem32` returns words ≥ `0x80000000` as negative numbers, so normalise them.
- Do **not** put `eeObj.AddHook` on branch instructions (e.g. `jr ra`) or delay slots: the game crashes.
- Hooks on overlay code stay put when the level changes, so they end up in the middle of other code. Install them per level.
- The JAK emulator needs `eeInsnReplace` (not `WriteMem32`) to patch already-compiled code such as `0x12710C`.
- An emulator `eboot.bin` only works with the `ps2-emu-compiler.self` from the same build
  ("jitShm Communication Area Size Mismatch" otherwise).
- `--ee-ignore-segfault` on JAK rejects the value `RW` (it accepts something else).
