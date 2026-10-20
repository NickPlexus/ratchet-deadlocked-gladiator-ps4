<div align="center">

# Ratchet: Deadlocked / Gladiator on PS4

**The first working setup of Ratchet: Deadlocked (US) and Ratchet: Gladiator (EU)<br>on Sony's official PS2-Classics emulator for PS4.**

[![Download](https://img.shields.io/badge/%E2%AC%87%EF%B8%8F%20DOWNLOAD-latest%20release-2ea44f?style=for-the-badge)](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)

![Status](https://img.shields.io/badge/status-playable-brightgreen?style=flat-square)
![Platform](https://img.shields.io/badge/platform-PS4%20(GoldHEN)-003791?style=flat-square&logo=playstation)
![Emulator](https://img.shields.io/badge/emulator-PS2%20Classics%20(Rogue%20Galaxy%20v1)-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)

[English](#-english) · [Русский](#-русский)

</div>

---

## 🇬🇧 English

### The problem

On the [PS4 PS2-Classics compatibility list](https://www.psdevwiki.com/ps4/PS2_Classics_Emulator_Compatibility_List)
Ratchet: Deadlocked has been marked **unplayable** for years: *"Black screen when going in-game"*. What that actually meant:

1. **Black screen.** On a stock package the game freezes on a black screen right after *New Game*. A Lua patch by
   Scalerize (PS4 Developer Wiki) got past it, but it was the only fix that existed, and the game was still broken behind it.
2. **A "melted" Ratchet.** With that patch and the config everyone shared, the game started, but character models were
   broken: Ratchet's skeleton was twisted, parts of his body were stretched into spikes, and limbs stuck out at wrong angles.
   The game's skeletal animation is computed on the PS2's VU0 vector unit, and that maths came out wrong.
3. **Crash on every kill.** In Deadlocked defeated enemies blow apart into pieces. Every time that happened (and on a wrench
   slam into the ground) the emulator crashed with `Unhandled PageFault` or the game froze. So you could not get through
   the very first arena, because killing enemies is the whole game.
4. **No multiplayer.** Local multiplayer crashed shortly after a match loaded (or, on another emulator build, started with
   headless and invisible players).

### What we found

- **The culprit was one setting in the commonly shared config.** It turned on *result clamping* for the vector units
  (`--vu0/vu1/cop2-no-clamping=0`, `--*-clamp-results=1`). Clamping is meant to imitate how the PS2 handles out-of-range
  floating-point numbers, but for this game it corrupts the bone matrices. The broken numbers then turn into broken memory
  addresses, and that is what crashed the emulator when enemies blew up.
- **How we found it.** After a day of chasing the problem inside the VU0 microcode and Lua with no progress, we switched
  *everything* off and brought the settings back **one at a time**:
  - with all maths simplified, Ratchet's model was suddenly **perfect**, but he was stuck in an endless "falling" animation (collision broke);
  - restoring accuracy settings one by one showed that `--cop2-opt-flags=0` fixes the collision and clamping is what twists the model;
  - with clamping off and `cop2-opt-flags=0`, **the model was correct and the explosion crashes were gone too**.
- **Multiplayer was crashing because of a safety patch.** A small Lua guard catches the game's broken bone writes. Its code sat in
  memory right next to the game's stack. The campaign never reached it, but multiplayer uses more stack, overwrote it and crashed.
  We moved the guard to an unused area at the end of RAM, and multiplayer works.

### Before / after

| | Before | Now |
|---|---|---|
| Starting a game | ❌ black screen (stock) | ✅ |
| Character models | ❌ twisted skeleton, spiky stretched limbs | ✅ correct |
| Defeating enemies (they explode) | ❌ emulator crash or freeze, every time | ✅ no crashes |
| Campaign | ❌ stuck in the first arena | ✅ playable |
| Local multiplayer | ❌ crash after the match loads | ✅ works |
| Sound, normal speed, 2x2 internal resolution | — | ✅ |
| Loading a save made **at Dreadzone Station** | ❌ | ❌ still freezes, see [Known issues](#known-issues) |

### ⬇️ Download

Click the green **DOWNLOAD** button at the top, or open **[Releases](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)**
and download **`ratchet-ps4-configs.zip`** from the *Assets* list.

> ⚠️ This project contains **no game files, ISO, PKG or Sony emulator files**. You need your own copy of the game and your own
> PS2-Classics package (FPKG). Only text configs and Lua scripts are distributed here.

### What you need

- A PS4 with a jailbreak and **GoldHEN**.
- Your own disc image of **Ratchet: Deadlocked (USA, SCUS-97465)** or **Ratchet: Gladiator (Europe, SCES-53285)**.
- A PS2-Classics FPKG maker (for example *PS2-FPKG*) and the **Rogue Galaxy (v1)** emulator.

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

Then put the two files into `/data/dl_patches/` over FTP (GoldHEN FTP). The emulator reads them on every launch, so you can
try changes without reinstalling. A full example is in `configs/package/`.
</details>

<details>
<summary><b>The key lines of the config</b></summary>

```ini
--vu0-no-clamping=1    --vu0-clamp-results=0
--vu1-no-clamping=1    --vu1-clamp-results=0
--cop2-no-clamping=1   --cop2-clamp-results=0
--cop2-opt-flags=0     # with 2, collision breaks and Ratchet "falls" forever
--cop2-accurate-mul=1
--fpu-no-clamping=0    --fpu-clamp-results=1
```
</details>

### For developers

- **[docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md)**: memory map and addresses (main loop, joint/VU0 routine, skinning writer,
  VIF1 kick, LZ decompressor and loader), how the Scalerize patch works, the emulator's Lua API, flags and pitfalls, WAD/LZ/text formats,
  what was tried and failed, open problems.
- **[docs/FINDINGS.md](docs/FINDINGS.md)**: the short story of the fixes.
- **[docs/MATHS_FINDINGS.md](docs/MATHS_FINDINGS.md)**: how we arrived at the maths settings, step by step, and what did and did not break.
- **[tools/](tools/)**: disassemblers, PCSX2 savestate patcher, a PS4-Lua simulator, the Insomniac LZ compressor, text tools.

### Known issues

- **Loading a save made at Dreadzone Station freezes** on the loading screen (US and EU). Saves made elsewhere load fine, and
  reaching the station during play works. **Workaround: don't save at the station.** It happens even with an empty config,
  so it is an emulator problem; it is being investigated.
- On the Russian-patched US image some textures smear when you get close (teleport pads). The EU version renders them correctly.
- Cutscene audio can end slightly before the video.

### FAQ

<details>
<summary><b>Will it work with another emulator?</b></summary>

Tested and recommended: **Rogue Galaxy v1**. Dark Chronicle v2 (the same emulator branch) loaded the levels in earlier tests
but was not retested with the final config. On *War of the Monsters* multiplayer starts but the geometry is broken. On the
*Jak & Daxter* emulator the models stay broken with any settings.
</details>

<details>
<summary><b>Where are the ISO / PKG?</b></summary>

Not here and never will be. Use your own copy of the game.
</details>

<details>
<summary><b>I want to help</b></summary>

Great! Open an *Issue* with what you found or a *Pull Request* with your change. The main open problem is the Dreadzone Station
save. All the technical details are in **[docs/FINDINGS.md](docs/FINDINGS.md)**.
</details>

---

## 🇷🇺 Русский

### В чём была проблема

В [списке совместимости PS2 Classics на PS4](https://www.psdevwiki.com/ps4/PS2_Classics_Emulator_Compatibility_List)
Ratchet: Deadlocked годами числилась **неиграбельной**:

1. **Чёрный экран** сразу после «Новой игры». Lua-патч Scalerize его обходил, но это было единственное исправление, и дальше игра всё равно была сломана.
2. **«Расплавленный» Рэтчет.** С этим патчем и конфигом, который все друг другу передавали, модели персонажей ломались: скелет Рэтчета
   перекручивало, части тела вытягивало шипами, руки и ноги торчали в разные стороны. Скелетную анимацию игра считает на векторном
   процессоре PS2 (VU0), и эта математика выходила неправильной.
3. **Вылет на каждом убийстве.** В Deadlocked побеждённые враги разлетаются на куски. В этот момент (и при ударе ключом об землю)
   эмулятор падал с ошибкой `Unhandled PageFault` или игра зависала. Пройти даже первую арену было невозможно.
4. **Мультиплеер** падал вскоре после загрузки матча.

### Что нашли

- **Виновата одна настройка из общего конфига:** ограничение значений (clamping) на векторных процессорах VU0/VU1/COP2. Для этой
  игры оно портит матрицы костей, а кривые числа превращаются в кривые адреса памяти. Отсюда и вылеты на взрывах.
- **Как нашли:** после целого дня безуспешной возни с микрокодом VU0 и Lua мы выключили всё и стали включать настройки **по одной**.
  С упрощённой математикой Рэтчет внезапно стал ровным, но вечно «падал». Дальше по одной строке нашли, что `--cop2-opt-flags=0`
  чинит падение, а clamping перекручивает модель. Без clamping ушли и перекручивание, и вылеты.
- **Мультиплеер ронял наш же страховочный патч:** его код лежал в памяти рядом со стеком игры, и мультиплеер его затирал.
  Перенесли его в свободную область, и мультиплеер заработал.

**Скачать:** зелёная кнопка **DOWNLOAD** вверху или раздел **[Releases](https://github.com/NickPlexus/ratchet-deadlocked-gladiator-ps4/releases/latest)**,
файл **`ratchet-ps4-configs.zip`**.

**Установка:** соберите FPKG своей копии игры на эмуляторе **Rogue Galaxy v1** и положите два файла для своей версии в папку
`patches` пакета (`SCUS-97465_*` для US, `SCES-53285_*` для EU). Образов и PKG здесь нет и не будет.

**Известная проблема:** не загружается сохранение, сделанное на Станции зоны ужаса. Не сохраняйтесь там, остальные сохранения работают.

**Для разработчиков:** карта адресов, устройство патчей, API и подводные камни эмулятора — в **[docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md)** (на английском), инструменты — в **[tools/](tools/)**.

**Русификатор** для EU-версии выйдет отдельно.

---

## Credits

- **[NickPlexus](https://github.com/NickPlexus)**: project lead, testing on real hardware, and the "switch everything off, bring it back one at a time" idea that cracked it.
- **Scalerize**: the original VU0 sync Lua that gets past the black screen (PS4 Developer Wiki).
- **kingkangyu/ps2-classics-emus**: emulator collection used for testing.
- Analysis, configs and Lua: made together with **Claude** (Anthropic).

## License

[MIT](LICENSE) for the configs, Lua code and tools of this project. The VU0 sync block inside the Lua files is the work of Scalerize
and is included with attribution.
