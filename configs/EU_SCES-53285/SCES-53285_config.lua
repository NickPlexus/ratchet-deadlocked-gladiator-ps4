-- Ratchet: Gladiator (PAL) SCES-53285: same Lua as the Deadlocked US v4 build.
-- The Scalerize VU0 patcher hooks core 0x12710C and returns to 0x127110: identical in the PAL core (checked
-- against a PAL PCSX2 savestate). The other patches verify the original words before writing, so they
-- only apply where the PAL code is identical.
-- Ratchet: Deadlocked (US), SCUS-97465
-- Author: Scalerize (as published on PS4 Developer Wiki)
-- Emulator configuration companion: War of the Monsters

apiRequest(0.1)

local eeObj = getEEObject()
local emuObj = getEmuObject()

local patcher = function()
    -- Jump to the VU0 synchronization patcher.
    eeObj.WriteMem32(0x0012710C, 0x0803FE80)

    -- Check whether patcher is needed.
    eeObj.WriteMem32(0x000FFA00, 0x3C1B7120)
    eeObj.WriteMem32(0x000FFA04, 0x377BCDA8)
    eeObj.WriteMem32(0x000FFA08, 0x3C02000F)
    eeObj.WriteMem32(0x000FFA10, 0xAC44FFF4)
    eeObj.WriteMem32(0x000FFA0C, 0x3442FA00)
    eeObj.WriteMem32(0x000FFA14, 0xAC45FFF0)
    eeObj.WriteMem32(0x000FFA18, 0x8C44FFFC)
    eeObj.WriteMem32(0x000FFA1C, 0x8C840000)
    eeObj.WriteMem32(0x000FFA20, 0x149B0003)
    eeObj.WriteMem32(0x000FFA28, 0x08049C44)
    eeObj.WriteMem32(0x000FFA2C, 0x241B0000)
    eeObj.WriteMem32(0x000FFA34, 0xAC43FFF8)
    eeObj.WriteMem32(0x000FFA38, 0x3C040010)
    eeObj.WriteMem32(0x000FFA3C, 0x24840004)
    eeObj.WriteMem32(0x000FFA40, 0x8C830000)
    eeObj.WriteMem32(0x000FFA44, 0x107B0003)
    eeObj.WriteMem32(0x000FFA4C, 0x1000FFFB)

    -- Patcher.
    eeObj.WriteMem32(0x000FFA54, 0xAC44FFFC)
    eeObj.WriteMem32(0x000FFA64, 0x3C030C03)
    eeObj.WriteMem32(0x000FFA68, 0x3463FE48)
    eeObj.WriteMem32(0x000FFA6C, 0xAC8300BC) -- First 6 vi01.
    eeObj.WriteMem32(0x000FFA78, 0xAC8301FC)
    eeObj.WriteMem32(0x000FFA84, 0xAC830354)
    eeObj.WriteMem32(0x000FFA90, 0xAC830494)
    eeObj.WriteMem32(0x000FFA9C, 0xAC8305EC)
    eeObj.WriteMem32(0x000FFAA8, 0xAC83072C)
    eeObj.WriteMem32(0x000FFAAC, 0x3C030C03)
    eeObj.WriteMem32(0x000FFAB0, 0x3463FE4B)
    eeObj.WriteMem32(0x000FFAB4, 0xAC83015C) -- First 4 vi02.
    eeObj.WriteMem32(0x000FFAC0, 0xAC8302AC)
    eeObj.WriteMem32(0x000FFACC, 0xAC8303F4)
    eeObj.WriteMem32(0x000FFAD8, 0xAC830544)

    -- Return.
    eeObj.WriteMem32(0x000FFC0C, 0x8C44FFF4)
    eeObj.WriteMem32(0x000FFC10, 0x8C45FFF0)
    eeObj.WriteMem32(0x000FFC14, 0x8C43FFF8)
    eeObj.WriteMem32(0x000FFC18, 0x08049C44)

    -- VI01 and VI02 burn cycles at 0x000FF904 via AdvanceClock.
    eeObj.WriteMem32(0x000FF914, 0x03E00008)
    eeObj.WriteMem32(0x000FF918, 0x241F0000)
    eeObj.WriteMem32(0x000FF920, 0x48C00800)
    eeObj.WriteMem32(0x000FF924, 0x1000FFF7)
    eeObj.WriteMem32(0x000FF92C, 0x48C01000)
    eeObj.WriteMem32(0x000FF930, 0x1000FFF4)
end

emuObj.AddVsyncHook(patcher)


-- ===== skinning store clamp, universal (all US levels + known PAL addresses) =====
-- The skinning writer stores two bone matrices through pointers packed in 128-bit v1 (sq at,16(v1) /
-- sq at,32(v1), then pcpyud). With bad joint data a pointer becomes 0x6FFFFF80 (bone -2) and the PS4
-- emulator page-faults (0x7007FF90). Each store goes through a stub: v1 = (v1 & 0x3FFF) | s4 (s4 = SPR).
-- Second store is always at +0x28 from the first. Sites are verified word by word before patching.
local CL_BASES = { 0x589558, 0x547C98, 0x534BF8, 0x54E2D8, 0x547018, 0x5589F8, 0x53BC58, 0x53C018, 0x560518, 0x533C98, 0x525540, 0x53CED8, 0x5DF718, 0x4F9D20, 0x58D838, 0x4FD200, 0x528AE0, 0x5374F8, 0x5385D8, 0x53F938, 0x53FB78, 0x540B78, 0x54ACF8, 0x54B8F8, 0x552038, 0x55C818, 0x564278, 0x5E20B8 }  -- US + PAL (all overlays)
local CL_CAVE16, CL_CAVE32 = 0x01FF0040, 0x01FF0000  -- v23: away from the stack (MP crash 0x0BFC0000)
local CL_ANDI, CL_OR, CL_PCPYUD = 0x30633FFF, 0x00741825, 0x70601BA9
local clBase = nil
local function clRd(a) local w = eeObj.ReadMem32(a); if w < 0 then w = w + 4294967296 end; return w end
local function clJ(t) return 0x08000000 + math.floor(t / 4) end
local function clOriginal(s)
    return clRd(s) == 0x7C610010 and clRd(s + 4) == CL_PCPYUD and clRd(s + 0x28) == 0x7C610020 and clRd(s + 0x2C) == CL_PCPYUD
end
emuObj.AddVsyncHook(function()
    if clBase then
        if clRd(clBase) == clJ(CL_CAVE16) then
            -- keep the stubs alive every frame (that memory is not guaranteed to stay intact)
            local c16 = { CL_ANDI, CL_OR, 0x7C610010, CL_PCPYUD, CL_ANDI, CL_OR, clJ(clBase + 8), 0 }
            local c32 = { CL_ANDI, CL_OR, 0x7C610020, CL_PCPYUD, CL_ANDI, CL_OR, clJ(clBase + 0x30), 0 }
            for i = 1, 8 do eeObj.WriteMem32(CL_CAVE16 + (i - 1) * 4, c16[i]); eeObj.WriteMem32(CL_CAVE32 + (i - 1) * 4, c32[i]) end
            return
        end
        clBase = nil
    end
    for _, s in ipairs(CL_BASES) do
        if clOriginal(s) then
            local c16 = { CL_ANDI, CL_OR, 0x7C610010, CL_PCPYUD, CL_ANDI, CL_OR, clJ(s + 8), 0 }
            local c32 = { CL_ANDI, CL_OR, 0x7C610020, CL_PCPYUD, CL_ANDI, CL_OR, clJ(s + 0x30), 0 }
            for i = 1, 8 do eeObj.WriteMem32(CL_CAVE16 + (i - 1) * 4, c16[i]); eeObj.WriteMem32(CL_CAVE32 + (i - 1) * 4, c32[i]) end
            eeObj.WriteMem32(s, clJ(CL_CAVE16)); eeObj.WriteMem32(s + 4, 0)
            eeObj.WriteMem32(s + 0x28, clJ(CL_CAVE32)); eeObj.WriteMem32(s + 0x2C, 0)
            clBase = s
            print(string.format("[DLPATCH] skinning store clamp applied at %06X", s))
            return
        end
    end
end)

-- ===== heartbeat: every ~5 s print a line (the log prefix shows the current EE PC) =====
local hb = 0
emuObj.AddVsyncHook(function()
    hb = hb + 1
    if hb % 300 == 0 then
        print(string.format("[DLHB] frame=%d", hb))
    end
end)
