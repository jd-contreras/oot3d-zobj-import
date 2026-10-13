// Choosing and applying. Picking in the lists only records the choice; nothing on the card
// changes until Apply_Patch, which adds or removes the Extra Buttons patch and puts the chosen
// models and voice in the game's mod folder. Models are copied over Link's files; a voice pack
// is copied in or, when a sound file is already there (the randomizer's shuffled music, or an
// earlier voice), lifted into it. The library is only ever read.
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "manager.h"
#include "unzip.h"
#include "voicelift.h"

static const char* const sTargets[KIND_COUNT] = {
    "/romfs/actor/zelda_link_boy_new.zar",
    "/romfs/actor/zelda_link_child_new.zar",
    "/romfs/sound/QueenSound.bcsar",
};

// ---- progress -----------------------------------------------------------------------------

void (*gProgressDraw)(const char* what, float fraction) = NULL;
static int sSteps = 1, sStep = 0, sLastShown = -1;
static const char* sWhat = "";

static void ProgressShow(float part) {
    if (!gProgressDraw) return;
    float fraction = ((sStep > 0 ? sStep - 1 : 0) + part) / (float)sSteps;
    if (fraction > 1) fraction = 1;
    // Drawing waits for the screen, so only draw when the bar would visibly move.
    const int shown = (int)(fraction * 100);
    if (shown == sLastShown) return;
    sLastShown = shown;
    gProgressDraw(sWhat, fraction);
}

void Progress_Begin(int steps) {
    sSteps = steps > 0 ? steps : 1;
    sStep = 0;
    sLastShown = -1;
    sWhat = "";
}

void Progress_Step(const char* what) {
    if (sStep < sSteps) sStep++;
    sWhat = what;
    sLastShown = -1;
    ProgressShow(0);
}

void Progress_Part(size_t done, size_t total) {
    if (total) ProgressShow((float)done / (float)total);
}

void Message_Add(char* msg, const char* fmt, ...) {
    const size_t used = strlen(msg);
    if (used + 2 >= MESSAGE_LEN) return;
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg + used, MESSAGE_LEN - used - 1, fmt, ap);
    va_end(ap);
    strcat(msg, "\n");
}

int Apply_UsesSlot(const Slot* slot) {
    switch (gSettings.region) {
        case REGION_USA:
            return slot == &gSlots[0];
        case REGION_EUR:
            return slot == &gSlots[1];
        default:
            return slot->folderExists;
    }
}

// ---- choosing -----------------------------------------------------------------------------

int Apply_IsChosen(int item) {
    return item >= 0 && strcmp(gSettings.chosen[gItems[item].kind], gItems[item].key) == 0;
}

void Apply_Choose(Kind kind, int item) {
    snprintf(gSettings.chosen[kind], KEY_LEN, "%s", item < 0 ? CHOICE_NONE : gItems[item].key);
    if (kind == KIND_VOICE) gSettings.linkVoice = 1; // picked on its own: see LinkVoice
    Settings_Save();
}

void Apply_ChooseSet(int character, int whole) {
    const Character* c = &gCharacters[character];
    for (int k = 0; k < KIND_COUNT; k++) {
        if (c->item[k] >= 0 || whole) Apply_Choose((Kind)k, c->item[k]);
    }
    gSettings.linkVoice = 0; // the voice came with the set
    Settings_Save();
}

static const u8 sKindFlags[KIND_COUNT] = { RANDOM_ADULT, RANDOM_CHILD, RANDOM_VOICE };

int Apply_Randomizes(Kind kind) {
    return (gSettings.random & RANDOM_SET) || (gSettings.random & sKindFlags[kind]);
}

int Apply_RandomOptionOn(RandomOption option) {
    switch (option) {
        case OPTION_SET:
            return (gSettings.random & RANDOM_SET) != 0;
        case OPTION_ALL:
            return (gSettings.random & RANDOM_KINDS) == RANDOM_KINDS;
        default:
            return (gSettings.random & sKindFlags[option - OPTION_ADULT]) != 0;
    }
}

void Apply_ToggleRandomOption(RandomOption option) {
    const int on = Apply_RandomOptionOn(option);
    if (option == OPTION_SET) gSettings.random = on ? 0 : RANDOM_SET;
    else if (option == OPTION_ALL) gSettings.random = on ? 0 : RANDOM_KINDS;
    else gSettings.random = (u8)((gSettings.random & ~RANDOM_SET) ^ sKindFlags[option - OPTION_ADULT]);
    Settings_Save();
}

int Apply_Hidden(Kind kind) {
    return gSettings.secret && Apply_Randomizes(kind);
}

// A whole character at random: the kinds it doesn't have go back to the game's own.
static int RandomSet(void) {
    int sets = 0;
    for (int i = 0; i < gCharacterCount; i++) sets += !gCharacters[i].hidden;
    if (!sets) return 0;
    int pick = rand() % sets;
    for (int i = 0; i < gCharacterCount; i++) {
        if (gCharacters[i].hidden || pick-- != 0) continue;
        for (int k = 0; k < KIND_COUNT; k++) {
            const int item = gCharacters[i].item[k];
            snprintf(gSettings.chosen[k], KEY_LEN, "%s", item < 0 ? CHOICE_NONE : gItems[item].key);
        }
        return 1;
    }
    return 0;
}

// One kind at random, from every item of that kind in the library.
static int RandomKind(Kind kind) {
    int count = 0;
    for (int i = 0; i < gItemCount; i++) count += gItems[i].kind == kind;
    if (!count) return 0;
    int pick = rand() % count;
    for (int i = 0; i < gItemCount; i++) {
        if (gItems[i].kind != kind || pick-- != 0) continue;
        snprintf(gSettings.chosen[kind], KEY_LEN, "%s", gItems[i].key);
        return 1;
    }
    return 0;
}

// A random voice is for this time only: it never becomes a character's remembered voice.
int Apply_RandomizeNow(void) {
    int picked = 0;
    if (gSettings.random & RANDOM_SET) {
        picked = RandomSet();
    } else {
        for (int k = 0; k < KIND_COUNT; k++) {
            if (Apply_Randomizes((Kind)k)) picked += RandomKind((Kind)k);
        }
    }
    if (picked && Apply_Randomizes(KIND_VOICE)) gSettings.linkVoice = 0;
    Settings_Save();
    return picked;
}

int Apply_Pending(Kind kind) {
    return gSettings.chosen[kind][0] && strcmp(gSettings.chosen[kind], gSettings.applied[kind]) != 0;
}

int Apply_ButtonsPending(const Slot* slot) {
    if (gSettings.buttons) return slot->state == SEED_READY;
    return slot->state == SEED_PATCHED && slot->hasBackup;
}

int Apply_AnyPending(void) {
    for (int k = 0; k < KIND_COUNT; k++) {
        if (Apply_Pending((Kind)k)) return 1;
    }
    for (int i = 0; i < SLOT_COUNT; i++) {
        if (Apply_ButtonsPending(&gSlots[i])) return 1;
    }
    return 0;
}

// ---- applying -----------------------------------------------------------------------------

// Copies a library item to `dst`: straight from its file, or unpacked from its zip.
static int CopyItem(const Item* item, const char* dst) {
    if (!item->entry[0]) return File_Copy(item->path, dst);
    size_t len = 0;
    u8* data = Item_Read(item, &len);
    const int ok = data && File_Write(dst, data, len);
    free(data);
    return ok;
}

// Puts a voice pack in use at `dst`. Returns NULL on success or what went wrong.
static const char* ApplyVoice(const Item* pack, const char* dst) {
    if (!File_Exists(dst)) return CopyItem(pack, dst) ? NULL : "could not copy the file (SD card full?)";
    size_t packLen = 0, targetLen = 0, outLen = 0;
    u8* packData = Item_Read(pack, &packLen);
    u8* target = packData ? File_Read(dst, &targetLen) : NULL;
    u8* out = NULL;
    const char* error = NULL;
    if (!packData || !target) {
        error = "the sound files could not be read";
    } else {
        switch (VoiceLift(packData, packLen, target, targetLen, &out, &outLen)) {
            case LIFT_OK:
                if (!File_Write(dst, out, outLen)) error = "could not write the sound file (SD card full?)";
                break;
            case LIFT_SAME:
                break;
            case LIFT_BAD_TARGET: // the file in the mod folder is unusable: replace it
                if (!File_Write(dst, packData, packLen)) error = "could not copy the file (SD card full?)";
                break;
            case LIFT_BAD_PACK:
                error = "this is not a voice pack the app can read";
                break;
            default:
                error = "not enough memory";
                break;
        }
    }
    free(packData);
    free(target);
    free(out);
    return error;
}

static int FindItem(const char* key) {
    for (int i = 0; i < gItemCount; i++) {
        if (strcmp(gItems[i].key, key) == 0) return i;
    }
    return -1;
}

// A voice lifted into the randomizer's music has no size or content of its own to compare
// later, so the sound file is marked as the app leaves it: its size, and a checksum of the
// start of Link's voice in it. A file the randomizer writes afterwards has the original voice
// there (or a different layout), so the mark no longer matches.
#define MARK_LEN 0x10000

static size_t MarkSpan(u32 size, u32 offset) {
    return size - offset < MARK_LEN ? size - offset : MARK_LEN;
}

static void MarkVoice(int slot, const char* dst) {
    memset(&gSettings.voiceMark[slot], 0, sizeof(gSettings.voiceMark[slot]));
    size_t len = 0, offset = 0;
    u8* data = File_Read(dst, &len);
    if (data && VoiceLift_Locate(data, len, &offset) && offset < len) {
        gSettings.voiceMark[slot].size = (u32)len;
        gSettings.voiceMark[slot].offset = (u32)offset;
        gSettings.voiceMark[slot].crc = Zip_Crc32(data + offset, MarkSpan((u32)len, (u32)offset));
    }
    free(data);
}

static int VoiceMarkMatches(int slot, const char* dst) {
    const u32 size = gSettings.voiceMark[slot].size, offset = gSettings.voiceMark[slot].offset;
    if (!size || offset >= size || File_Size(dst) != (long)size) return 0;
    const size_t span = MarkSpan(size, offset);
    u8* part = malloc(span);
    const int ok = part && File_ReadAt(dst, (long)offset, part, span) && Zip_Crc32(part, span) == gSettings.voiceMark[slot].crc;
    free(part);
    return ok;
}

// Puts the choice for one kind in the game's mod folder. Returns NULL on success or what went
// wrong. A model that was already applied and whose file is still the same size is left alone
// (a restore after a new seed); anything newly chosen is always copied.
static const char* ApplyKind(Kind kind) {
    const char* choice = gSettings.chosen[kind];
    const int none = strcmp(choice, CHOICE_NONE) == 0;
    const int item = none ? -1 : FindItem(choice);
    if (!none && item < 0) return "the chosen file is no longer in OoTModelManager";
    const int fresh = strcmp(choice, gSettings.applied[kind]) != 0;
    int slots = 0;
    for (int i = 0; i < SLOT_COUNT; i++) {
        if (!Apply_UsesSlot(&gSlots[i])) continue;
        slots++;
        char dst[PATH_LEN];
        Seed_Path(&gSlots[i], sTargets[kind], dst);
        if (none) {
            remove(dst);
        } else if (kind == KIND_VOICE) {
            const char* error = ApplyVoice(&gItems[item], dst);
            if (error) return error;
            MarkVoice(i, dst);
        } else if (fresh || File_Size(dst) != gItems[item].size) {
            if (!CopyItem(&gItems[item], dst)) return "could not copy the file (SD card full, or a damaged zip?)";
        }
    }
    if (!slots) return "no OoT3D folder in luma/titles yet. Make a seed first, or set the game region";
    snprintf(gSettings.applied[kind], KEY_LEN, "%s", choice);
    return NULL;
}

// A voice picked on its own becomes the voice of the chosen adult and child characters that
// have no voice pack of their own: written to their uses file, so the set keeps that voice
// from now on (also when Randomize picks it). Picking another voice later replaces it.
static void LinkVoice(char* msg) {
    const char* choice = gSettings.chosen[KIND_VOICE];
    const int voice = strcmp(choice, CHOICE_NONE) == 0 ? -1 : FindItem(choice);
    if (voice < 0 && strcmp(choice, CHOICE_NONE) != 0) return;
    int done[2] = { -1, -1 };
    for (int k = KIND_ADULT; k <= KIND_CHILD; k++) {
        const int model = FindItem(gSettings.chosen[k]);
        if (model < 0) continue;
        const int ci = gItems[model].character;
        Character* c = &gCharacters[ci];
        const int ownVoice = c->item[KIND_VOICE] >= 0 && !c->borrowed[KIND_VOICE];
        if (ownVoice || ci == done[0] || (voice >= 0 && gItems[voice].character == ci)) continue;
        const char* name = voice >= 0 ? gItems[voice].label : NULL;
        if (strcasecmp(c->uses[KIND_VOICE], name ? name : "") == 0) continue; // already so
        done[k] = ci;
        if (!Library_SetUses(ci, KIND_VOICE, name)) continue;
        if (name) Message_Add(msg, "%s now uses %s's voice.", c->name, name);
        else Message_Add(msg, "%s now has no voice of its own.", c->name);
    }
}

void Apply_Verify(void) {
    int changed = 0;
    for (int k = 0; k < KIND_COUNT; k++) {
        char* applied = gSettings.applied[k];
        if (!applied[0]) continue;
        const int none = strcmp(applied, CHOICE_NONE) == 0;
        const int item = none ? -1 : FindItem(applied);
        int ok = 1, slots = 0;
        for (int i = 0; i < SLOT_COUNT && ok; i++) {
            if (!Apply_UsesSlot(&gSlots[i])) continue;
            slots++;
            char dst[PATH_LEN];
            Seed_Path(&gSlots[i], sTargets[k], dst);
            const long size = File_Size(dst);
            if (none) ok = size < 0;
            else if (k == KIND_VOICE) ok = VoiceMarkMatches(i, dst);
            else ok = size >= 0 && (item < 0 || size == gItems[item].size);
        }
        if (!ok || !slots) {
            applied[0] = '\0';
            changed = 1;
        }
    }
    if (changed) Settings_Save();
}

int Apply_Patch(char* msg) {
    int problems = 0;
    // A custom adult or child model needs the seed's Custom Tunic Colors off (see merge.h).
    const int customModel = FindItem(gSettings.chosen[KIND_ADULT]) >= 0 || FindItem(gSettings.chosen[KIND_CHILD]) >= 0;
    static const char* const kindSteps[KIND_COUNT] = { "Adult model", "Child model", "Voice" };
    int steps = 0;
    for (int i = 0; i < SLOT_COUNT; i++) steps += gSlots[i].state != SEED_MISSING;
    for (int k = 0; k < KIND_COUNT; k++) steps += gSettings.chosen[k][0] != '\0';
    Progress_Begin(steps);
    // Extra Buttons: on adds it to a new seed, off puts a patched seed's own file back.
    for (int i = 0; i < SLOT_COUNT; i++) {
        Slot* s = &gSlots[i];
        if (s->state != SEED_MISSING) Progress_Step(gSettings.buttons ? "Extra Buttons" : "Removing Extra Buttons");
        if (gSettings.buttons) {
            if (s->state == SEED_READY) problems += !Seed_Patch(s, customModel, msg);
            else if (s->state == SEED_PATCHED) {
                Message_Add(msg, "%s seed: already has Extra Buttons.", s->name);
                Seed_Update(s, customModel, msg);
            }
            else if (s->state == SEED_UNSUPPORTED) {
                problems++;
                Message_Add(msg, "%s seed: made by a randomizer version this app can't patch.", s->name);
            }
        } else if (s->state == SEED_PATCHED && s->hasBackup) {
            Seed_Undo(s, msg);
        }
    }
    Seed_ScanAll(); // a patched seed's folder now exists for the models

    int done = 0, failed = 0, hidden = 0;
    for (int k = 0; k < KIND_COUNT; k++) {
        if (!gSettings.chosen[k][0]) continue; // never chosen: left as it is on the card
        Progress_Step(Apply_Hidden((Kind)k) ? "Models and voice" : kindSteps[k]);
        const char* error = ApplyKind((Kind)k);
        if (error) {
            failed++;
            Message_Add(msg, "%s: not changed, %s.", gKindNames[k], error);
        } else {
            done++;
            hidden += Apply_Hidden((Kind)k);
            if (k == KIND_VOICE && gSettings.linkVoice) LinkVoice(msg);
        }
    }
    gSettings.linkVoice = 0;
    Settings_Save();
    if (hidden) Message_Add(msg, "Picked in secret. Start the game to find out.");
    else if (done && !failed) Message_Add(msg, "Your models and voice are in place.");
    if (!msg[0]) Message_Add(msg, "Nothing to do: no new seed and nothing chosen yet.");
    return problems + failed;
}
