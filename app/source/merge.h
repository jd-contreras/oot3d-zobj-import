// Puts the Extra Buttons patch under an OoT3D Randomizer seed's code.ips.
// Plain C with no 3DS calls, so it is also built and tested on a PC (test_host.c).
// Same method as the OoT3D Model Importer's tools/seedmerge.py.
#pragma once

#include <stddef.h>
#include <stdint.h>

#define MERGE_REGION_USA 0
#define MERGE_REGION_EUR 1

// A randomizer data symbol a seed can write, with where it sits in our build.
typedef struct {
    uint32_t addr; // 0 if this randomizer build doesn't have the symbol
    uint32_t size; // 0 if it runs to the end (the custom text)
} MergeSymbol;

// Symbols in the order the randomizer writes them into a seed (source/patch.cpp).
enum {
    SYM_ITEM_OVERRIDES,
    SYM_ENTRANCE_OVERRIDES,
    SYM_SETTINGS,
    SYM_SPOILER_DATA,
    SYM_SPOILER_LOCS,
    SYM_SCRUB_PRICES,
    SYM_SHOP_PRICES,
    SYM_DUNGEON_REWARDS,
    SYM_CUSTOM_MESSAGES,
    SYM_MESSAGE_ENTRIES_PTR,
    SYM_MESSAGE_ENTRIES_COUNT,
    SYM_BGM_OVERRIDES,
    SYM_SFX_DATA,
    SYM_DUNGEON_INFO,
    SYM_DUNGEON_IMPORTANCE,
    SYM_GS_LOC_OVERRIDES,
    SYM_ENEMY_OVERRIDES,
    SYM_COUNT
};

// One Extra Buttons patch: a randomizer build for one game region.
typedef struct {
    const char* source;     // randomizer version, for messages
    const char* file;       // base patch file name
    int region;             // MERGE_REGION_*
    uint32_t randoStart;    // first address of the randomizer's own code
    uint32_t addedBytes;    // game bytes our patch changes on top of the randomizer's
    uint32_t settingsRegion; // offset of the region setting in the seed's settings
    uint32_t settingsTunics; // offset of Custom Tunic Colors (the four rainbow tunic settings follow)
    MergeSymbol symbols[SYM_COUNT];
} MergeBuild;

typedef enum {
    MERGE_OK = 0,
    MERGE_NOT_IPS,         // not an IPS patch, or cut short
    MERGE_OTHER_BUILD,     // from a randomizer build this patch is not for
    MERGE_ALREADY_PATCHED, // already has Extra Buttons (starts with this exact base patch)
    MERGE_NOT_A_SEED,      // right build, but its records don't look like a seed's
    MERGE_WRONG_REGION,    // settings and code are for different regions
    MERGE_NO_MEMORY,
} MergeResult;

// Checks whether `seed` (a seed's code.ips) was made by the randomizer build `base` is for.
// Returns MERGE_OK, MERGE_ALREADY_PATCHED, MERGE_OTHER_BUILD, MERGE_NOT_IPS or MERGE_NO_MEMORY.
MergeResult Merge_Identify(const uint8_t* seed, size_t seedLen, const uint8_t* base, size_t baseLen,
                           const MergeBuild* build);

// Writes the merged code.ips to a newly allocated buffer (free() it). Call after Merge_Identify
// returned MERGE_OK for this build.
// dropTunics: turn the seed's Custom Tunic Colors (and rainbow tunics) off. With that setting on,
// the randomizer swaps in tunic colour data made for Link's own model; an imported model's
// tunic parts are not in it, so every tunic would show the model's default colour.
// tunicsWereOn: receives whether the seed had any of those settings on (may be NULL).
MergeResult Merge_Apply(const uint8_t* seed, size_t seedLen, const uint8_t* base, size_t baseLen,
                        const MergeBuild* build, int dropTunics, int* tunicsWereOn, uint8_t** out, size_t* outLen);
