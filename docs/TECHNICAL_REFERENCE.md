# Technical reference: Ratchet: Deadlocked / Gladiator internals and the PS4 PS2-Classics emulator

Everything we learned in about two days of reverse engineering, written so that a developer (or an LLM) can pick it up and continue.
Addresses are EE (Emotion Engine) virtual addresses for **Ratchet: Deadlocked USA, SCUS-97465** unless marked **EU**
(Ratchet: Gladiator, SCES-53285). The core (boot ELF) is identical between US and EU at every address listed in the core section;
level overlays differ.

Verification legend: **[PS4]** observed on the real console (klog / Lua), **[PCSX2]** observed in PCSX2 savestates,
**[static]** from disassembly only, **[hyp]** hypothesis, not proven.

Contents:
1. [Memory map](#1-memory-map)
2. [Core: main loop, vsync](#2-core-main-loop-and-vsync)
3. [Joint-blend routine and the VU0 microprogram](#3-joint-blend-routine-and-the-vu0-microprogram)
4. [Skinning writer and the bone-index −2 bug](#4-skinning-writer-and-the-bone-index-2-bug)
5. [VIF1 DMA kick and the explosion crash](#5-vif1-dma-kick-and-the-explosion-crash)
6. [Level loading: LZ decompressor and loader](#6-level-loading-lz-decompressor-and-loader)
7. [The Scalerize Lua patcher, explained](#7-the-scalerize-lua-patcher-explained)
8. [Our Lua patches](#8-our-lua-patches)
9. [The emulator: flags, Lua API, quirks](#9-the-ps4-ps2-classics-emulator)
10. [Disc data, WAD/LZ format, text and font](#10-disc-data-wad-lz-and-text)
11. [What was tried and failed](#11-what-was-tried-and-failed)
12. [Open problems](#12-open-problems)

---

## 1. Memory map

| Range | What | Source |
|---|---|---|
| `0x00100000` | VU0 microprogram image (VIF MPG packet) uploaded by the game, see §3 | [PCSX2] |
| `0x0011A180–0x00163B80` | core `.text` (Project RYNO decomp layout) | [static] |
| `0x0021E180–~0x00680000` | level overlays are loaded here (`levels/*/overlay.elf` in a Wrench unpack) | [static] |
| `0x003F0E80` | level vtable (`lvl.vtbl`, RYNO) | [static] |
| `0x003F1000–0x0054D700` | overlay `.text` (RYNO layout) | [static] |
| `0x0034DE40` | temporary bone-matrix buffer (23 matrices) that a fromSPR DMA fills from scratchpad (DMA issued at `0x589B50`) | [PCSX2] |
| `0x00223790` | pointer to the current DMA packet | [PS4] |
| `0x001711A8` | loader state struct; byte `+0x13` (`0x1711BB`) is tested by the loader at `0x579DE4` (save/continue branch) | [static] |
| `0x70000000–0x70003FFF` | scratchpad (SPR), 16 KB. Skinning input stream at `0x70002000`, matrices at `0x70002F00`, bone slots `0x70000000 + idx*64` | [PS4][PCSX2] |
| `0x000FF900–0x000FFC20` | Scalerize patcher code + data (§7) | [PS4] |
| `0x000FFD60` and up | **game stack area on PS4**. Anything you put just below `0x100000` can be overwritten (our old clamp stubs at `0xFFD00` were) | [PS4] |
| `0x00080000–0x00100000` | periodically zeroed or used on PS4 (we saw our code at `0xA0000` wiped by PC `0x81FC0`) | [PS4] |
| `0x01FEB800–0x01FFA400` | never held non-zero data in our scans: **safe code cave** (we use `0x1FF0000`) | [PS4] |

## 2. Core: main loop and vsync

| Address | What |
|---|---|
| `0x001270C0` | `WaitVSync`: installs a handler (`jal 0x126F10`), clears VBLANK in `INTC_STAT` (`0x1000F000` ← 4), then loops |
| `0x00127110–0x00127124` | the wait loop: `lw v0,0(0x1000F000); andi 4; bne → exit; lw v0,0(sp); beq v0,zero → loop` |
| `0x0012710C` | a `nop` right before the loop: **Scalerize's hook point** (replaced with `j 0x000FFA00`) |
| `0x00138DD8` | the **only** caller of `WaitVSync` in gameplay: return address of the main loop's frame wait (60 calls/s) [PS4] |
| `0x00529F38` | a large per-frame function of the level-1 overlay (57 calls); *not* the top-level loop, despite what we first assumed |

Sampling the EE PC once per second on the console shows `0x127110`/`0x127120` most of the time in normal play: the game is mostly waiting for vsync.

## 3. Joint-blend routine and the VU0 microprogram

This routine computes the skeleton (joint matrices) for animated models. It is the root of the "twisted model" problem.

- One copy in every level overlay plus one in the boot/menu code: **15 different bases**, identical layout.
  The full list per level is in [`data/handshake_sites.json`](data/handshake_sites.json). Examples: boot/menu `0x440020`,
  `1_dreadzone_station` (level 1, US) `0x53CC08`, multiplayer maps `0x4B6DE8`, MP menu `0x5A2890`.
- The routine starts a **persistent VU0 microprogram** with `vcallms 0` at `base − 0xB8` and then feeds it joint data through
  `vf1..vf8`, reading results from `vf9..vf12`.
- **Handshake protocol** (12 points at `base + {0x0, 0xA0, 0x140, 0x1F0, 0x298, 0x338, 0x3D8, 0x488, 0x530, 0x5D0, 0x670, 0x728}`):
  EE does `ctc2 zero, vi1` / `ctc2 zero, vi2` ("data ready"); the microprogram spins until the flag is cleared, reads the inputs and
  sets the flag back to 1 (VU0 code `0xE0–0x108`, `0x1B8–0x1E0`). **The EE never checks the flag**: about 24 instructions later it
  overwrites `vf1..vf8` and reads the results, relying on VU0 having finished in time.
- Signature used to find the routine: word `0x7120CDA8`. In the US level-1 dump it appears at `0x53CB4C`, `0x53CDF4`, `0x53D08C`;
  **EU** at `0x53F404`, `0x53F6AC`, `0x53F944`.
- The microprogram image is in core RAM at `0x100090` (a VIF MPG packet; a second MPG header at `+0x800` shifts micro addresses ≥ `0x800` by 8 bytes in the image).
- A routine at `0x53C818` (level 1) does `qmfc2 s6, vf11` at `0x53CC50`; putting the I-bit (interlock) on all `qmfc2` makes the game hang there [PCSX2].
- The microprogram uses `rsqrt`; the emulator logs `WARN: RSQRT_S used - MSW/PS4 determinism WILL NOT MATCH!`.
- In PCSX2 the "twisted model" is reproduced by running the EE at 300% (EE faster than VU0 → mixed joint data). Fixing the handshake
  cures PCSX2 at 300% **but not the PS4**. On the PS4 the twisting turned out to be caused by **VU result clamping** (§9.2).

## 4. Skinning writer and the bone-index −2 bug

- The skinning code stores two bone matrices through pointers packed in a 128-bit register: `sq at,16(v1)`, then `pcpyud`, and
  `sq at,32(v1)` 0x28 bytes later. The pointer is built by the skinning interpreter (`0x589638`, level 1) from data that a DMA puts
  in scratchpad (`0x70002010`).
- With bad joint data the bone index becomes −2 and the pointer becomes `0x6FFFFF80` (= SPR − 0x80). The PS4 emulator page-faults
  (`0x7007FF90` / `0x7007FFA0` in crash dumps; EE PC `0x589580` on level 1). PCSX2 does not crash here.
- Store pairs (first `sq`, the second is at `+0x28`): US level 1 `0x589558`; **EU** level 1 `0x58D838`; MP menu `0x5DF718`;
  all MP maps `0x4F9D20`. The complete table (US + EU, 28 bases) is `CL_BASES` in the Lua.
- Mob joint buffers: `moby + 0x58` (pointer), joint count at `moby + 0x57`; `UpdateMobyJoints 0x58A648 → 0x58A440 → 0x589950` (level 1) [PCSX2].
- Moby/joint data is otherwise identical between a good and a broken run; only the temp buffer `0x34DE40` and 4 SPR matrices at `0x70002F00` differ [PCSX2].

## 5. VIF1 DMA kick and the explosion crash

- Every overlay has one place that starts the VIF1 (geometry) DMA: `sw v1 → D1_CHCR` (`0x10009000`). Level 1: `0x6340E0` (store), EE PC
  `0x6340EC` in crash dumps. All 15 addresses: [`data/vif1_kick_sites.json`](data/vif1_kick_sites.json).
- **Symptom with clamping on:** when an enemy blows apart (or on a wrench slam) the emulator crashes with `Unhandled PageFault` inside
  its own DMA code, reading EE memory at offset `0x4001C000` (its scratchpad mapping is at `0x40000000`, so that is ~110 KB past the
  16 KB SPR). Other times the game just stops drawing: VIF1 DMA finished (`D1_CHCR=0x700000C5`), VIF1/GIF idle, EE in `WaitVSync`.
- All VIF1 chains we walked from Lua were structurally valid (cnt/next/ref, up to ~5700 tags, no loops).
- **[hyp]** A tag sourcing from SPR with a length past `0x4000` (real hardware wraps SPR addresses mod 16 KB, the emulator does not),
  produced by corrupted effect data. It disappears completely once VU clamping is off, so we did not pursue it.

## 6. Level loading: LZ decompressor and loader

- **LZ decompressor** (persistent, `0x583A48–0x583C50`): reads compressed bytes from SPR (`t7 = 0x70000000`, double buffer at `0x2000`)
  and streams the source in **8 KB chunks** with a **toSPR DMA** (channel `0x1000D400`):
  - `0x583C70`: start chunk: `SADR=t6` (+0x80), `QWC=512` (+0x20), `MADR=t3` (+0x10), `CHCR=0x100` (+0x0);
  - `0x583C90`: wait until `CHCR.STR` clears;
  - `0x583C50`: exit (`out = a1 .. t5`); `0x583C68`: `jr ra` (**do not hook it**, see §9.4).
- Decompression chain of a level load (deterministic): `0x857000` (640 B), `0x1EADF80` (284 672 B), `0xA89F60` (14.2 MB),
  `0x6C7000` (1.16 MB), mission data (`0x181E4C0`, `0x1879270`, sizes depend on the mission), then `0x6C7000` (2.39 MB),
  and last a small one (6812 B) **over the start of** `0x6C7000`.
- **Loader** after the last decompression (US, `0x579C00…`; returns at `0x579DAC`):
  `0x579DB8 jal 0x5BA3F0` (a0 = `0x6C7000`) → `0x579DD4 jal 0x57CA28` → `0x579DE4 lbu flag 0x1711BB` →
  (flag 0) `0x579E28 … jal 0x583FC0` → `0x579E48 jal 0x578258` → `0x579E68 jal 0x653560` → `0x579E88` →
  later `0x578258` is called again from core `0x3CB578` (a state machine) → the game loop (`WaitVSync` from `0x138DD8`).
  Callers of each decompression: `ra = 0x578AE8, 0x579ABC, 0x579B78, 0x579BF0, 0x579C50, 0x579DAC`.

## 7. The Scalerize Lua patcher, explained

The well-known Lua by Scalerize (PS4 Developer Wiki) that gets past the black screen. What it does:

1. Every vsync it writes `j 0x000FFA00` at `0x12710C` (inside `WaitVSync`), so the patcher runs once per frame.
2. Code at `0xFFA00`: `k1 = 0x7120CDA8`; saves `a0/a1/v1` at `0xFF9F4/0xFF9F0/0xFF9F8`; reads the last found address from `0xFF9FC`.
   If that word still equals the signature it returns (`j 0x127110`); otherwise it **scans RAM upward from `0x100004`** for the
   signature (no upper bound), stores the address and writes `jal 0x000FF920`/`jal 0x000FF92C` stubs (`0x0C03FE48`/`0x0C03FE4B`)
   over 10 of the 12 `ctc2 zero, vi1/vi2` handshake points (offsets `+0xBC, +0x1FC, +0x354, +0x494, +0x5EC, +0x72C` for vi1 and
   `+0x15C, +0x2AC, +0x3F4, +0x544` for vi2, relative to the signature).
3. The stubs (`0xFF904–0xFF934`) do the `ctc2` and burn cycles: the emulator option `--ee-hook=0x000FF904,AdvanceClock,,397` advances
   the EE clock by 397 cycles there, giving VU0 time to finish.

Without it the game hangs on a black screen after *New Game* (and loading any save also hangs) on every emulator donor we tried.

## 8. Our Lua patches

- **Skinning guard** (`CL_BASES`, Lua): for each known store pair whose original words match (`0x7C610010` + `0x70601BA9` and
  `0x7C610020` + `0x70601BA9` at `+0x28`), replace both stores with `j` to stubs that do `andi v1,v1,0x3FFF; or v1,v1,s4` (s4 = SPR base),
  so a broken pointer lands inside scratchpad instead of faulting. Stubs are rewritten every vsync.
  **Stubs must live at `0x1FF0000`/`0x1FF0040`**: at `0xFFD00`/`0xFFD40` multiplayer's deeper stack overwrote them, which crashed MP
  with EE PC `0x0BFC0000` / `0x800002F8`. [PS4]
- **Heartbeat**: prints every 300 vsyncs; the klog line prefix shows the current EE PC, a cheap sampler.
- Diagnostics we used (not in the release): VIF1 chain walker at the kick site, `WaitVSync` caller counter (hook `0x1270C0`),
  decompressor/loader tracer (§6).

## 9. The PS4 PS2-Classics emulator

### 9.1 Builds ("donors")

| Donor | Branch / date | Flags | Result |
|---|---|---|---|
| **Rogue Galaxy v1** | revoke 270 | ~270 | ✅ recommended |
| Dark Chronicle v2 | newer, 281 flags (`--lua-use-pcall`, `--emulog-file`) | 281 | behaves like Rogue |
| War of the Monsters | `olympack/master`, 2015, revoke 256 | older | MP starts, broken geometry; no `--audio-stretching` |
| JAK (Jak & Daxter) | `titles/Jak1-TPL` #1599, 2017, revoke 270 | 384 | needs `eeInsnReplace`; models broken with any maths settings |

- An `eboot.bin` only works with the `ps2-emu-compiler.self` from the **same build**, otherwise
  `jitShm Communication Area Size Mismatch, ps2_compiler probably needs rebuilt`.
- Jak 2/3/X donors have packed eboots (flags not readable).

### 9.2 The maths settings (the fix)

| Setting | Effect on Deadlocked |
|---|---|
| `--vu0/vu1/cop2-no-clamping=0` + `--*-clamp-results=1` (common config) | **twisted skeleton, crashes on enemy explosions** |
| all three clamping **off** | correct models, no explosion crashes |
| `--cop2-opt-flags=2` (unsafe flag optimisation) | collision fails: Ratchet "falls" forever (and enemies did not spawn in our test) |
| `--cop2-opt-flags=0` | collision OK |
| `--cop2-accurate-mul=1`, FPU clamping on | harmless, kept |
| `--vu0/cop2-use-rsqrt=0`, `--*-use-rcp=0`, `--cop2-accurate-addsub=1` (tested on top of the clamping config) | Ratchet fell through the floor |
| `--vu1=jit` | tested and used; `jit-sync` together with clamping off was not properly tested |
| `--gs-uprender=2x2` | works; some multi-second GS stalls (`SubmitDone: 5986ms`) in heavy cutscenes on US |

### 9.3 Lua API (`apiRequest(0.1)`, enumerated with `--lua-debug-api=1`)

- `eeObj`: `AddHook(pc, opcode, fn)`/`RemoveHook`, `DmaAddHook`, `Get/SetGpr`, `Get/SetFpr`, `GetPc/SetPc`, `ReadMem8..128`,
  `WriteMem8..128`, `ReplaceMem*`, `SchedulerDelayEvent`.
- Globals: `eeInsnReplace`, `InsnOverlay`, `eeDebugBreak`, `iopInsnReplace`, `getEEObject`, `getEmuObject`, `getIOPObject`, `getDmaObject`, `getGsObject`.
- `emuObj`: `AddVsyncHook`, `AddGifTagHook`, `AddSectorReadHook`, `AddEntryPointHook`, `GetPad`, `SetFrameLimiter`, `PsBindShader`.
- No access to VU registers or VU memory.
- `print()` goes to klog (GoldHEN, TCP port 3232) and to the emulog file.

### 9.4 Quirks and pitfalls

- `ReadMem32` returns words ≥ `0x80000000` as **negative** numbers: normalise (`if w < 0 then w = w + 2^32 end`).
- `apiRequest(2.0)`, or hooks installed before the level code is in memory, crash at start (SIGILL). Install hooks from a vsync hook
  once the target word is present.
- **Never hook a branch (`jr ra`) or a delay slot**: the game crashes (we got EE PC `0x55D480`).
- Hooks stay at their address when an overlay is replaced: they end up in the middle of other code and crash it (EE PC `0x34032000`).
  Install hooks per level and remove them on level change.
- JAK build: `WriteMem32` to already-compiled code (`0x12710C`) is not seen by the JIT. Use `eeInsnReplace(addr, old, new)`.
- `--ee-pc-coherency=1` puts the exact EE PC into crash dumps (deprecated on JAK).
- `--path-patches=/data/...` lets you edit `<TITLE>_cli.conf` and `<TITLE>_config.lua` over FTP without reinstalling.
  The emulator also looks for `<TITLE>_lopnor.cfgbin` (Sony's own patch format, not studied).
- `--detect-idle-chcr=0` makes the game hang forever in a DMA poll loop. `--vu0` accepts only `jit`.
- JAK: `--ee-ignore-segfault` exists with the hint `[none,R,W,RW]`, but `RW` is rejected (`Unrecognized or missing parameter for 'mode [0,R,RW]'`).
- Hidden debug flags: `--lua-debug-api`, `--vu-jit-disasm`, `--ee-jit-disasm=[0,1=mips,2=x86]`, `--eTrace=` (channels e-dmac, e-vif1,
  e-gif, e-sched, e-jit, e-mem, …), `--ee-block-validation=[PageProt,ShortHash,Hash,None]`.

## 10. Disc data, WAD, LZ and text

- Unpack and repack with **Wrench** (chaoticgd). A full repack rebuilds every `LEVELn.WAD` and **the repacked levels do not load**
  on hardware/emulators, so patch blocks in place instead (`tools/translation/iso_patch.py`).
- **Insomniac LZ** (format documented in `tools/translation/lz_dl.py`): literal / far match / match / little match packets; the stream
  is consumed in **0x2000-byte chunks** and no packet may straddle a chunk (pad packet `0x12 00 00` + `0xEE` filler).
  `lz_dl.py` compresses tighter than Wrench (menu table 104 KB vs 125 KB).
- **Text:** the main language table (`globals/misc/boot/english.bin`, 4482 strings: 16-byte records `{u32 offset, u16 id, 8×FF, …}` +
  NUL-terminated strings) is stored **95 times** on the disc (boot WAD + 2 copies in every level WAD), each LZ-compressed in its own slot.
  Cutscene subtitles (`globals/mpeg/*/*.asset`, 407 strings) are uncompressed `<text>\0<text>\0` pairs; some videos exist twice on the disc.
- **Font:** the game has no Cyrillic; Russian patches draw Cyrillic glyphs over Latin capitals
  (`A=А B=В C=С D=Д E=Е F=Г G=Ж H=Н J=Ь K=К L=Л M=М N=И O=О P=Р Q=Ц R=Я S=Ы T=Т U=Ю V=Ф W=Ш X=Х Y=У Z=П 3=З 4=Ч 6=Б`);
  lowercase is reserved for tags like `[circle]`; codes `{80xx}` (line break, colour) must be kept.
- The 2008 Russian patch (CompileISO `.DLT`) rewrites ~105 MB of WAD data. On that image some textures smear up close on the PS4;
  the EU image with the same config does not show it.
- PCSX2 GameDB has `EETimingHack` for SCUS-97465 ("Fixes SPR errors while going in-game").

## 11. What was tried and failed

So nobody has to repeat it:

- Making the EE↔VU0 handshake explicit (EE waits for the VU0 flag): on the PS4 VU0 does not progress while the EE spins → hang.
- A fully synchronous scheme (microprogram stops at each wait, EE re-calls it with `vcallms`): no effect on the PS4.
- Translating the whole VU0 microprogram to EE COP2 macro code (`tools/lab/vu0_to_ee.py`, 1151 EE instructions): works in PCSX2, no effect on the PS4.
- FPU accuracy (`--fpu-accurate-*`), `--ee-cycle-scalar` 1.5/2.0, larger `AdvanceClock` values, `clamp-operands`: no effect.
- Re-copying stale toSPR data / synchronous fromSPR: data in SPR was already correct.
- Lua VIF1 chain walker (blocking bad tags): chains were valid; the walker itself only slowed the game.

All of those targeted symptoms. The real cause was the clamping setting (§9.2).

## 12. Open problems

1. **A save made at Dreadzone Station freezes on loading** (US and EU; other saves load; reaching the station by playing works).
   The loader takes exactly the same path as a working load up to `0x578258` called from `0x3CB578` (§6), then the EE stops completely
   (even vsync hooks stop firing). Not fixed by: an empty config, Scalerize only, IOP at full speed (`--iop-cycle-scalar` default),
   the old clamping config, removing the skinning guard, bounding the Scalerize scan with a sentinel. Without Scalerize the load hangs
   even earlier. **Next step:** reproduce in PCSX2 and find what the loader waits for there (IOP / SIF RPC, CDVD, a semaphore).
2. US Russian-patched image: textures smear up close (teleport pads, cutscene frame). EU is fine → probably the Russian WAD rewrite.
3. On the War of the Monsters donor MP geometry is broken (headless / invisible player) whatever the config.
4. Cutscene audio ends a little before the video.
