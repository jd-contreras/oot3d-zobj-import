// The randomizer seeds in luma/titles: what state each is in, adding the Extra Buttons patch
// to one, and putting the seed's own file back. The patches for each supported randomizer
// version are in the app's romfs (the site's own, see gen_builds.py); the merge itself is in merge.c.
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "builds.h"
#include "manager.h"

#define TITLES_DIR "sdmc:/luma/titles/"
#define SEED_NAME "/code.ips"
#define BACKUP_NAME "/code_before_extra_buttons.ips"

Slot gSlots[SLOT_COUNT] = {
    { "USA", "0004000000033500", MERGE_REGION_USA, SEED_MISSING, -1, 0, 0, 0 },
    { "Europe", "0004000000033600", MERGE_REGION_EUR, SEED_MISSING, -1, 0, 0, 0 },
};

void Seed_Path(const Slot* slot, const char* file, char* out) {
    snprintf(out, PATH_LEN, TITLES_DIR "%s%s", slot->titleId, file);
}

const char* Seed_BuildName(const Slot* slot) {
    return slot->build >= 0 ? gBuilds[slot->build].source : "";
}

// Looks at the seed in a slot's folder and works out what can be done with it.
static void ScanSlot(Slot* slot) {
    char path[PATH_LEN];
    slot->build = -1;
    Seed_Path(slot, "", path);
    DIR* dir = opendir(path);
    slot->folderExists = dir != NULL;
    if (dir) closedir(dir);
    Seed_Path(slot, BACKUP_NAME, path);
    slot->hasBackup = (u8)File_Exists(path);
    Seed_Path(slot, SEED_NAME, path);
    if (!File_Exists(path)) {
        slot->state = SEED_MISSING;
        return;
    }
    size_t seedLen = 0;
    u8* seed = File_Read(path, &seedLen);
    if (!seed) {
        slot->state = SEED_UNREADABLE;
        return;
    }
    slot->state = SEED_UNSUPPORTED;
    for (int i = 0; i < BUILD_COUNT && slot->state == SEED_UNSUPPORTED; i++) {
        if (gBuilds[i].region != slot->region) continue;
        size_t baseLen = 0;
        u8* base = File_Read(gBuilds[i].file, &baseLen);
        if (!base) continue;
        switch (Merge_Identify(seed, seedLen, base, baseLen, &gBuilds[i])) {
            case MERGE_OK:
                slot->state = SEED_READY;
                slot->build = i;
                break;
            case MERGE_ALREADY_PATCHED:
                slot->state = SEED_PATCHED;
                slot->build = i;
                break;
            case MERGE_NOT_IPS:
                slot->state = SEED_UNREADABLE;
                break;
            default:
                break;
        }
        free(base);
    }
    free(seed);
}

void Seed_ScanAll(void) {
    for (int i = 0; i < SLOT_COUNT; i++) ScanSlot(&gSlots[i]);
}

#define TUNICS_OFF_NOTE "The randomizer's Custom Tunic Colors are off for this seed: custom models use their own."

int Seed_Patch(Slot* slot, int dropTunics, char* msg) {
    if (slot->state != SEED_READY) return 0;
    const MergeBuild* build = &gBuilds[slot->build];
    char seedPath[PATH_LEN], backupPath[PATH_LEN];
    Seed_Path(slot, SEED_NAME, seedPath);
    Seed_Path(slot, BACKUP_NAME, backupPath);
    size_t seedLen = 0, baseLen = 0, outLen = 0;
    u8* seed = File_Read(seedPath, &seedLen);
    u8* base = File_Read(build->file, &baseLen);
    u8* out = NULL;
    const char* error = NULL;
    int tunicsWereOn = 0;
    if (!seed || !base) {
        error = "could not read the files";
    } else {
        switch (Merge_Apply(seed, seedLen, base, baseLen, build, dropTunics, &tunicsWereOn, &out, &outLen)) {
            case MERGE_OK:
                break;
            case MERGE_WRONG_REGION:
                error = "this seed is for the other game region";
                break;
            case MERGE_NO_MEMORY:
                error = "out of memory";
                break;
            default:
                error = "this file is not a randomizer seed";
                break;
        }
    }
    // Keep the seed's own file before anything is replaced.
    if (!error && !File_Write(backupPath, seed, seedLen)) error = "could not write the backup (SD card full?)";
    if (!error && !File_Write(seedPath, out, outLen)) error = "could not write code.ips (SD card full?)";
    slot->patchedNow = (u8)(error == NULL);
    if (error) Message_Add(msg, "%s seed: buttons not added, %s.", slot->name, error);
    else Message_Add(msg, "%s seed: Extra Buttons added.", slot->name);
    if (!error && dropTunics && tunicsWereOn) Message_Add(msg, TUNICS_OFF_NOTE);
    free(seed);
    free(base);
    free(out);
    ScanSlot(slot);
    return error == NULL;
}

void Seed_Update(Slot* slot, int dropTunics, char* msg) {
    if (slot->state != SEED_PATCHED || !slot->hasBackup) return;
    const MergeBuild* build = &gBuilds[slot->build];
    char seedPath[PATH_LEN], backupPath[PATH_LEN];
    Seed_Path(slot, SEED_NAME, seedPath);
    Seed_Path(slot, BACKUP_NAME, backupPath);
    size_t seedLen = 0, baseLen = 0, outLen = 0, nowLen = 0;
    // The seed's own file is the backup: patch it again and see if the result differs.
    u8* seed = File_Read(backupPath, &seedLen);
    u8* base = File_Read(build->file, &baseLen);
    u8* now = File_Read(seedPath, &nowLen);
    u8* out = NULL;
    int tunicsWereOn = 0;
    if (seed && base && now &&
        Merge_Apply(seed, seedLen, base, baseLen, build, dropTunics, &tunicsWereOn, &out, &outLen) == MERGE_OK &&
        (outLen != nowLen || memcmp(out, now, outLen) != 0)) {
        if (!File_Write(seedPath, out, outLen)) Message_Add(msg, "%s seed: could not update code.ips.", slot->name);
        else if (dropTunics) Message_Add(msg, TUNICS_OFF_NOTE);
        else Message_Add(msg, "%s seed: the randomizer's Custom Tunic Colors are back on.", slot->name);
    }
    free(seed);
    free(base);
    free(now);
    free(out);
    ScanSlot(slot);
}

void Seed_Undo(Slot* slot, char* msg) {
    if (!slot->hasBackup) return;
    char seedPath[PATH_LEN], backupPath[PATH_LEN];
    Seed_Path(slot, SEED_NAME, seedPath);
    Seed_Path(slot, BACKUP_NAME, backupPath);
    if (File_Copy(backupPath, seedPath)) {
        remove(backupPath);
        slot->patchedNow = 0;
        Message_Add(msg, "%s seed: Extra Buttons removed.", slot->name);
    } else {
        Message_Add(msg, "%s seed: could not restore the backup.", slot->name);
    }
    ScanSlot(slot);
}
