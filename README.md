<div align="center">

# Ratchet: Deadlocked / Gladiator on PS4

**Configs and Lua patches that make Ratchet: Deadlocked (US) and Ratchet: Gladiator (EU) playable<br>on Sony's official PS2-Classics emulator for PS4.**

[![Download](https://img.shields.io/badge/%E2%AC%87%EF%B8%8F%20DOWNLOAD-latest%20release-2ea44f?style=for-the-badge)](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)

![Status](https://img.shields.io/badge/status-playable-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-PS4%20(GoldHEN)-003791?style=flat-square&logo=playstation)
![Emulator](https://img.shields.io/badge/emulator-PS2%20Classics%20(Rogue%20Galaxy%20v1)-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)

[English](#-english) · [Русский](#-русский)

</div>

---

## 🇬🇧 English

### Before and after

Ratchet: Deadlocked was considered **unplayable** on the PS4 PS2-Classics emulator: Ratchet's model was twisted, the game crashed on every
enemy explosion, and multiplayer would not start. With these files:

| | Before | Now |
|---|:---:|:---:|
| Ratchet's model | ❌ twisted | ✅ correct |
| Killing / blowing up enemies | ❌ crash or freeze | ✅ works |
| Campaign | ❌ | ✅ playable |
| Multiplayer (local) | ❌ crash | ✅ works |
| Sound, full speed, 2x2 render | — | ✅ |
| Loading a save made **at Dreadzone Station** | ❌ | ❌ still freezes (see [Known issues](#known-issues)) |

### ⬇️ Download

Click the green **DOWNLOAD** button above, or open **[Releases](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)**
and download **`ratchet-ps4-configs.zip`** from the *Assets* list.

> ⚠️ This project contains **no game files, ISO, PKG or Sony emulator files**. You need your own legally obtained copy of the game
> and your own PS2-Classics package (FPKG). Only text configs and Lua scripts are distributed here.

### What you need

- A PS4 with a jailbreak and **GoldHEN**.
- Your own disc image of **Ratchet: Deadlocked (USA, SCUS-97465)** or **Ratchet: Gladiator (Europe, SCES-53285)**.
- A PS2-Classics FPKG maker (for example *PS2-FPKG*) and the **Rogue Galaxy (v1)** emulator donor.

### Installation

1. Build the game package with your FPKG tool using the **Rogue Galaxy v1** emulator.
2. Copy the two files for your version into the package's `patches` folder:

   | Version | Files |
   |---|---|
   | Deadlocked (USA) | `US_SCUS-97465/SCUS-97465_cli.conf` + `SCUS-97465_config.lua` |
   | Gladiator (Europe) | `EU_SCES-53285/SCES-53285_cli.conf` + `SCES-53285_config.lua` |

3. Build, install, play.

<details>
<summary><b>Tip: edit the configs without rebuilding the package</b></summary>

In the package's `config-emu-ps4.txt`, point the patch folder to the PS4's data partition:

```
--path-patches="/data/dl_patches"
```

Then put the two files into `/data/dl_patches/` over FTP (GoldHEN FTP). The emulator reads them on every launch,
so you can try changes without reinstalling. A full example is in `configs/package/`.
</details>

### What the fix actually is

**1. One wrong setting from the commonly shared config.** It turned on result clamping for VU0, VU1 and COP2 (the PS2 vector units).
That single thing caused both the twisted skeleton and the explosion crashes. The working maths:

```ini
--vu0-no-clamping=1    --vu0-clamp-results=0
--vu1-no-clamping=1    --vu1-clamp-results=0
--cop2-no-clamping=1   --cop2-clamp-results=0
--cop2-opt-flags=0     # with 2, collision breaks and Ratchet "falls" forever
--cop2-accurate-mul=1
```

It was found by elimination: switch *everything* off, then bring the settings back one at a time.

**2. The Lua patch:**
- **VU0 synchronisation** by **Scalerize** (PS4 Developer Wiki). Without it the game freezes on a black screen after *New Game*.
- **A skinning guard.** In some situations the game writes a bone matrix through a broken pointer; the guard redirects it into scratchpad.
  Its code lives at `0x1FF0000`. In its old place, next to the game's stack, multiplayer overwrote it and crashed.

All the debugging details are in **[docs/FINDINGS.md](docs/FINDINGS.md)**.

### Known issues

- **Loading a save made at Dreadzone Station freezes** on the loading screen (US and EU). Saves made elsewhere load fine,
  and reaching the station during play works. **Workaround: don't save at the station.** Under investigation.
- On the Russian-patched US image some textures smear up close (e.g. teleport pads). The EU version is fine.
- Cutscene audio can end slightly before the video.

### FAQ

<details>
<summary><b>Will it work with another emulator donor?</b></summary>

Tested and recommended: **Rogue Galaxy v1**. Dark Chronicle v2 (same emulator branch) loaded the levels in earlier tests but was not retested with the final config. On *War of the Monsters* multiplayer starts but the geometry is broken.
On the *Jak & Daxter* emulator the model stays broken with any settings.
</details>

<details>
<summary><b>Where are the ISO / PKG?</b></summary>

Not here and not going to be. Use your own copy of the game.
</details>

<details>
<summary><b>Can I improve it?</b></summary>

Yes, please! Open an *Issue* with what you found, or a *Pull Request* with your change. The station save bug is the main open problem.
</details>

---

## 🇷🇺 Русский

**Ratchet: Deadlocked** (US) и **Ratchet: Gladiator** (EU) теперь играбельны на прошитой PS4 через официальный эмулятор PS2 Classics.
Рэтчет ровный, враги взрываются без вылетов, работают кампания и мультиплеер, звук, нормальная скорость и рендер 2x2.

**Скачать:** зелёная кнопка **DOWNLOAD** вверху страницы или раздел **[Releases](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)**,
файл **`ratchet-ps4-configs.zip`**.

**Установка:** соберите FPKG игры на эмуляторе **Rogue Galaxy v1** и положите два файла для своей версии в папку `patches` пакета
(`SCUS-97465_*` для US, `SCES-53285_*` для EU). Образов и PKG здесь нет и не будет: нужна своя копия игры.

**Суть фикса:** в конфиге выключено ограничение значений (clamping) на VU0/VU1/COP2. Именно оно перекручивало Рэтчета и роняло игру на взрывах.

**Известная проблема:** не загружается сохранение, сделанное на Станции зоны ужаса. Не сохраняйтесь там, остальные сохранения работают.

**Русификатор** для EU-версии будет выпущен отдельно.

---

## Credits

- **[NickPlexus](https://github.com/NickPlexus)**: project lead, testing on real hardware, and the "switch everything off, bring it back one at a time" idea that cracked it.
- **Scalerize**: the original VU0 sync Lua (PS4 Developer Wiki).
- **kingkangyu/ps2-classics-emus**: emulator donor collection used for testing.
- Analysis, configs and Lua: made together with **Claude** (Anthropic).

## License

[MIT](LICENSE) for the configs, Lua code and tools of this project. The VU0 sync block inside the Lua files is the work of Scalerize
and is included with attribution.
