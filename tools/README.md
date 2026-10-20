# Tools

Small Python tools written during the investigation. Python 3; some need `numpy`, `zstandard`, `lupa`.
None of them contain game data: they work on your own disc image, Wrench unpack or PCSX2 savestates.

| Tool | What it does |
|---|---|
| `ee_dis.py` | Tiny R5900 (EE) disassembler for the opcodes we needed. `python ee_dis.py file.elf 0x127080 0x127140` |
| `lab/vu_dis.py` | VU micro-mode disassembler (upper + lower pairs). |
| `lab/pine.py` | Minimal PCSX2 PINE client: read/write EE memory of a running PCSX2. |
| `lab/statepatch.py` | Read/patch/write EE memory inside a PCSX2 `.p2s` savestate. Paths via env vars `DL_SSTATE`, `DL_BOOT_ELF`, `DL_LVL1_OVERLAY`. |
| `lab/lua_sim.py` | Runs an emulator config Lua against real memory from a PCSX2 savestate with a mocked PS4 Lua API (signed `ReadMem32` like the PS4), then writes the result into another slot. Great for testing Lua patches without a console. |
| `lab/matdiff.py` | Compares two memory dumps and finds 4×4 float matrices that are sane in one and broken in the other. |
| `lab/vu0_handshake.py` | Experiment: make the EE wait for the VU0 flag at the 12 handshake points (works in PCSX2, not on PS4). |
| `lab/sync_patch.py` | Experiment: synchronous EE↔VU0 scheme for the joint routine (works in PCSX2, not on PS4). |
| `lab/vu0_to_ee.py` | Experiment: translates the joint-blend VU0 microprogram into EE COP2 macro code (1151 instructions). |
| `translation/lz_dl.py` | Insomniac WAD LZ compressor (format documented in the file), tighter than Wrench's. `python lz_dl.py in out` |
| `translation/check_wad_chunks.py` | Verifies the 0x2000-byte chunk rule of a compressed WAD block. |
| `translation/text_tool.py` | Export/import the language table and cutscene subtitles to/from TSV (from a Wrench unpack). |
| `translation/find_text_blocks.py`, `iso_patch.py` | Patch edited text straight into a copy of the ISO (all 95 copies of the table + subtitles), no full repack. They expect the original project folder layout (Wrench path, backup table); adjust the constants at the top. |

See [`../docs/TECHNICAL_REFERENCE.md`](../docs/TECHNICAL_REFERENCE.md) for what the addresses mean.
