# Maths settings: how we got here, what each change did, what we did not see break

This document is about the emulator's **maths settings** only (clamping, accuracy, optimisation flags). The sequence is the
one we actually ran on a PS4 (GoldHEN, fw 13.52) with the Rogue Galaxy v1 donor. "Not seen break" means: noticed in play and
logs, not a proof that nothing else changed.

## How we got there

1. **Starting point: the common config** (`--*-clamp-results=1`, `--*-no-clamping=0`, `--cop2-opt-flags=0`, `--vu1=jit-sync`).
   Ratchet's skeleton was twisted and enemy explosions crashed the emulator.
2. **Dead ends.** For about a day we blamed the joint-blend VU0 microprogram and its handshake with the EE, wrote Lua to
   fix it, and tested in PCSX2 at 300% EE speed, which reproduced the twist there. Fixing the handshake cured PCSX2
   but not the PS4. Details: [TECHNICAL_REFERENCE.md §3 and §11](TECHNICAL_REFERENCE.md).
3. **The switch-everything-off test.** We set every maths option to its fast, unsafe value (no clamping, `cop2-opt-flags=2`,
   `cop2-accurate-mul=0`, optimisation flags 2) and then brought them back one at a time. This was the turning point.

## The sequence of single changes

Each row is a step from the fast config, with the observed result. Nothing else changed between steps.

| Step | Change | Observed |
|---|---|---|
| A | everything fast: no clamping on VU0/VU1/COP2, `cop2-opt-flags=2`, `cop2-accurate-mul=0`, FPU no clamping | model correct, Ratchet stuck "falling", enemies did not spawn |
| B | step A + `cop2-accurate-mul=1` | still falling, model correct |
| C | step B + FPU clamping on | still falling |
| D | step C + `cop2-opt-flags=0` | **Ratchet walks, model correct, explosions do not crash** |
| E | step D + VU0/COP2 accurate rsqrt/rcp + `cop2-accurate-addsub=1` | Ratchet falls through the floor (rejected) |
| F | common config = clamping ON on VU0/VU1/COP2 | model twisted, crash on explosions (the starting point) |

So the decisive setting is **clamping on the VU units**, and the one that stops collision is **`cop2-opt-flags=2`**.

## What we did not see break (with the final config)

Noticed in play and in logs; not exhaustively tested.

- **Movement and jumping, Ratchet's model**: normal in the campaign, skins menu, and the lobby.
- **Enemy kills and explosions**: no crash, no freeze, across the first levels we played.
- **Local multiplayer**: starts and plays once the skinning guard sits at `0x1FF0000` (before that it crashed).
- **Sound**: works with the IOP at 0.38 scalar (the sound-related setting we kept from the original config).
- **Frame rate**: normal speed with the frame limiter on. The "everything off" fast mode was far too fast.
- **2x2 render**: works; some multi-second GS stalls in heavy US cutscenes (`SubmitDone` warnings).
- **Textures**: no visible problems on EU; US Russian-patched image has smeared textures close up, independent of these settings.

## What we did not test

- **`--vu1=jit-sync` with clamping off**: the one run that tried it froze while loading level 1. We went back to `jit`.
- **Each VU clamping flag separately**: we switched VU0, VU1 and COP2 together. We do not know which of the three matters most.
- **Other accuracy options** on top of step D (`--fpu-accurate-*`, `--vu-to-double`) were tested only with clamping on.
- **Full playthrough**: we did not finish the campaign or every level, so there may be effects we have not seen.
- **Other donors with the same maths**: only Rogue v1 was run through the full chain; JAK and War of the Monsters broke for different reasons.

## Practical advice

- If you hit a twisted model, first check the clamping lines, not the Lua.
- If Ratchet falls forever, check `--cop2-opt-flags`.
- Change one line at a time and watch the emulator log; keep a copy of the config that works.
