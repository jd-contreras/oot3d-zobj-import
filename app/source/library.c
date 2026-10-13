// The mod library, sdmc:/OoTModelManager: one folder (or importer .zip) per character holding converted
// files under any name (an adult model, a child model, a voice pack), or loose files. What a
// file is comes from its contents, never from its name. Also the player's last choices, kept
// in a small text file in the same folder.
#include <ctype.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "manager.h"
#include "unzip.h"
#include "voicelift.h"

#define ZIP_MAX_ENTRIES 64
#define SETTINGS_FILE LIBRARY_DIR "/settings.txt"
#define README_FILE LIBRARY_DIR "/How to add characters.txt"
#define USES_FILE "uses.txt"

const char* const gKindNames[KIND_COUNT] = { "Adult", "Child", "Voice" };

Item gItems[MAX_ITEMS];
int gItemCount;
Character gCharacters[MAX_CHARACTERS];
int gCharacterCount;
Settings gSettings;

static u32 Le32(const u8* p) {
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16) | ((u32)p[3] << 24);
}

// Enough of a file's start to tell what it is (a model archive's name table is in there).
#define HEAD_LEN 0x10000

// What the file starting with `head` is, or -1. A Link model archive names its first file
// under "boy/" (adult) or "child/"; a voice pack is a sound archive.
static int ClassifyBytes(const u8* head, size_t len) {
    if (VoiceLift_IsArchive(head, len)) return KIND_VOICE;
    if (len < 0x20 || memcmp(head, "ZAR\x01", 4) != 0) return -1;
    const u32 meta = Le32(head + 0x10);
    if (meta > len || len - meta < 8) return -1;
    const u32 name = Le32(head + meta + 4);
    if (name > len || len - name < 6) return -1;
    if (memcmp(head + name, "boy/", 4) == 0) return KIND_ADULT;
    if (memcmp(head + name, "child/", 6) == 0) return KIND_CHILD;
    return -1;
}

static int ClassifyFile(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return -1;
    u8* head = malloc(HEAD_LEN);
    const int kind = head ? ClassifyBytes(head, fread(head, 1, HEAD_LEN, f)) : -1;
    free(head);
    fclose(f);
    return kind;
}

static int EndsWith(const char* s, const char* ext) {
    const size_t n = strlen(s), m = strlen(ext);
    return n >= m && strcasecmp(s + n - m, ext) == 0;
}

// "Saria_Adult.zar" -> "Saria Adult"; the importer's "oot3d-Saria.zip" -> "Saria"
static void Tidy(char* out, const char* file) {
    if (strncasecmp(file, "oot3d-", 6) == 0 && file[6]) file += 6;
    snprintf(out, NAME_LEN, "%s", file);
    char* dot = strrchr(out, '.');
    if (dot && dot != out) *dot = '\0';
    for (char* p = out; *p; p++) {
        if (*p == '_') *p = ' ';
    }
}

u8* Item_Read(const Item* item, size_t* len) {
    if (!item->entry[0]) return File_Read(item->path, len);
    ZipEntry* entries = malloc(ZIP_MAX_ENTRIES * sizeof(ZipEntry));
    u8* data = NULL;
    const int count = entries ? Zip_List(item->path, entries, ZIP_MAX_ENTRIES) : 0;
    for (int i = 0; i < count && !data; i++) {
        if (strcmp(entries[i].name, item->entry) == 0) data = Zip_Read(item->path, &entries[i], 0, len);
    }
    free(entries);
    return data;
}

static int AddCharacter(const char* name) {
    if (gCharacterCount >= MAX_CHARACTERS) return -1;
    Character* c = &gCharacters[gCharacterCount];
    memset(c, 0, sizeof(*c));
    snprintf(c->name, NAME_LEN, "%s", name);
    for (int k = 0; k < KIND_COUNT; k++) c->item[k] = -1;
    return gCharacterCount++;
}

// `file`: the file's own name, for its label. `entry`: its path inside a zip, or "".
static void AddItem(int character, const char* path, const char* entry, const char* file, long size, int kind) {
    if (character < 0 || gItemCount >= MAX_ITEMS) return;
    Item* it = &gItems[gItemCount];
    snprintf(it->path, PATH_LEN, "%s", path);
    snprintf(it->entry, sizeof(it->entry), "%s", entry);
    snprintf(it->key, KEY_LEN, entry[0] ? "%s|%s" : "%s", path, entry);
    it->size = size;
    it->kind = (Kind)kind;
    it->character = character;
    Tidy(it->label, file);
    Character* c = &gCharacters[character];
    if (c->item[kind] < 0) c->item[kind] = gItemCount;
    gItemCount++;
}

static int IsFolder(const char* path, const struct dirent* e) {
#ifdef HOST_TEST
    (void)e;
    return HostIsDir(path);
#else
    if (e->d_type == DT_DIR) return 1;
    if (e->d_type != DT_UNKNOWN) return 0;
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

static const char* const sKeys[KIND_COUNT] = { "adult=", "child=", "voice=" };

// Reads a character's uses file: "voice=Saria" borrows that piece from another library item.
static void ReadUses(Character* c) {
    if (!c->usesPath[0]) return;
    FILE* f = fopen(c->usesPath, "r");
    if (!f) return;
    char line[NAME_LEN + 16];
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = '\0';
        for (int k = 0; k < KIND_COUNT; k++) {
            const size_t n = strlen(sKeys[k]);
            if (strncasecmp(line, sKeys[k], n) == 0) snprintf(c->uses[k], NAME_LEN, "%s", line + n);
        }
    }
    fclose(f);
}

static void ScanCharacterFolder(const char* folder, const char* name) {
    DIR* dir = opendir(folder);
    if (!dir) return;
    int character = -1;
    struct dirent* e;
    while ((e = readdir(dir)) != NULL) {
        char path[PATH_LEN];
        if (e->d_name[0] == '.' || snprintf(path, sizeof(path), "%s/%s", folder, e->d_name) >= (int)sizeof(path)) continue;
        const int kind = ClassifyFile(path);
        if (kind < 0) continue;
        if (character < 0) character = AddCharacter(name);
        AddItem(character, path, "", e->d_name, File_Size(path), kind);
    }
    closedir(dir);
    if (character >= 0) {
        Character* c = &gCharacters[character];
        if (snprintf(c->usesPath, PATH_LEN, "%s/" USES_FILE, folder) >= PATH_LEN) c->usesPath[0] = '\0';
        ReadUses(c);
    }
}

// A zip or a loose file has no folder of its own: its uses file sits next to it.
static void SidecarUses(int character, const char* fileName) {
    if (character < 0) return;
    Character* c = &gCharacters[character];
    if (snprintf(c->usesPath, PATH_LEN, LIBRARY_DIR "/%s.uses.txt", fileName) >= PATH_LEN) c->usesPath[0] = '\0';
    ReadUses(c);
}

// The voice folder is "Voice"; a few likely spellings are taken as the same thing.
static int IsVoiceFolderName(const char* name) {
    static const char* const names[] = { VOICE_FOLDER, VOICE_FOLDER "s", "Sound", "Sounds" };
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        if (strcasecmp(name, names[i]) == 0) return 1;
    }
    return 0;
}

// One voice pack of the voice folder, listed under Voice as `name`.
static void AddVoice(const char* name, const char* path, const char* entry, const char* file, long size) {
    char tidy[NAME_LEN];
    Tidy(tidy, name);
    const int character = AddCharacter(tidy);
    if (character < 0) return;
    gCharacters[character].hidden = 1;
    AddItem(character, path, entry, file, size, KIND_VOICE);
}

#define VOICE_FOLDER_DEPTH 6 // deep enough for an importer zip extracted as it is

// The voice folder: each voice pack in it is listed under Voice. They are not characters, so
// they don't show under Sets and Randomize never picks them. A pack can be a loose .bcsar
// (named by its file), the importer's zip as it is (named by the zip), or that zip extracted
// into a folder (named by the folder).
static void ScanVoiceFolder(const char* folder, const char* topName, int depth) {
    DIR* dir = opendir(folder);
    if (!dir) return;
    struct dirent* e;
    while ((e = readdir(dir)) != NULL) {
        char path[PATH_LEN];
        if (e->d_name[0] == '.' || snprintf(path, sizeof(path), "%s/%s", folder, e->d_name) >= (int)sizeof(path)) continue;
        const char* name = topName ? topName : e->d_name;
        if (IsFolder(path, e)) {
            if (depth < VOICE_FOLDER_DEPTH) ScanVoiceFolder(path, name, depth + 1);
        } else if (EndsWith(e->d_name, ".zip")) {
            ZipEntry* entries = malloc(ZIP_MAX_ENTRIES * sizeof(ZipEntry));
            const int count = entries ? Zip_List(path, entries, ZIP_MAX_ENTRIES) : 0;
            for (int i = 0; i < count; i++) {
                if (!EndsWith(entries[i].name, ".bcsar")) continue;
                size_t headLen = 0;
                u8* head = Zip_Read(path, &entries[i], 0x40, &headLen);
                if (head && ClassifyBytes(head, headLen) == KIND_VOICE) {
                    AddVoice(name, path, entries[i].name, e->d_name, (long)entries[i].size);
                }
                free(head);
            }
            free(entries);
        } else if (ClassifyFile(path) == KIND_VOICE) {
            AddVoice(name, path, "", e->d_name, File_Size(path));
        }
    }
    closedir(dir);
}

// A .zip in the library is a character: the models and voice pack found inside it (as in a
// zip made by the OoT3D Model Importer; anything else in it, like a code.ips, is ignored).
static void ScanZip(const char* path, const char* fileName) {
    ZipEntry* entries = malloc(ZIP_MAX_ENTRIES * sizeof(ZipEntry));
    const int count = entries ? Zip_List(path, entries, ZIP_MAX_ENTRIES) : 0;
    int character = -1;
    for (int i = 0; i < count; i++) {
        const ZipEntry* z = &entries[i];
        if (!EndsWith(z->name, ".zar") && !EndsWith(z->name, ".bcsar")) continue;
        size_t headLen = 0;
        u8* head = Zip_Read(path, z, HEAD_LEN, &headLen);
        const int kind = head ? ClassifyBytes(head, headLen) : -1;
        free(head);
        if (kind < 0) continue;
        if (character < 0) {
            char name[NAME_LEN];
            Tidy(name, fileName);
            character = AddCharacter(name);
        }
        const char* slash = strrchr(z->name, '/');
        AddItem(character, path, z->name, slash ? slash + 1 : z->name, (long)z->size, kind);
    }
    free(entries);
    SidecarUses(character, fileName);
}

// Gives each character the pieces its uses file names. A name is the label an item shows in
// the lists: a character's name, or a voice-folder file's name.
static void ResolveUses(void) {
    for (int i = 0; i < gCharacterCount; i++) {
        Character* c = &gCharacters[i];
        for (int k = 0; k < KIND_COUNT; k++) {
            if (c->borrowed[k]) {
                c->item[k] = -1;
                c->borrowed[k] = 0;
            }
            if (c->item[k] >= 0 || !c->uses[k][0]) continue;
            for (int j = 0; j < gItemCount && c->item[k] < 0; j++) {
                if (gItems[j].kind == (Kind)k && gItems[j].character != i && strcasecmp(gItems[j].label, c->uses[k]) == 0) {
                    c->item[k] = j;
                    c->borrowed[k] = 1;
                }
            }
        }
    }
}

int Library_SetUses(int character, Kind kind, const char* name) {
    Character* c = &gCharacters[character];
    if (!c->usesPath[0]) return 0;
    snprintf(c->uses[kind], NAME_LEN, "%s", name ? name : "");
    char text[KIND_COUNT * (NAME_LEN + 8)];
    int n = 0;
    for (int k = 0; k < KIND_COUNT; k++) {
        if (c->uses[k][0]) n += snprintf(text + n, sizeof(text) - n, "%s%s\n", sKeys[k], c->uses[k]);
    }
    int ok = 1;
    if (n) ok = File_Write(c->usesPath, (const u8*)text, (size_t)n);
    else remove(c->usesPath);
    ResolveUses();
    return ok;
}

static int CompareCharacters(const void* a, const void* b) {
    return strcasecmp(((const Character*)a)->name, ((const Character*)b)->name);
}

void Library_Scan(void) {
    gItemCount = 0;
    gCharacterCount = 0;
    // The library, its voice folder and the how-to note are made if they are not there. The
    // note is the app's own, so an older copy of it is brought up to date.
    mkdir(LIBRARY_DIR, 0777);
    mkdir(LIBRARY_DIR "/" VOICE_FOLDER, 0777);
    {
        static const char text[] =
            "OoT Model Manager\r\n\r\n"
            "Make one folder per character in here and put its converted files inside:\r\n"
            "  an adult model (.zar), a child model (.zar) and/or a voice pack (.bcsar).\r\n"
            "The file names don't matter. The folder name is what the app shows.\r\n"
            "Or drop in the .zip the OoT3D Model Importer gives you, as it is: the zip is the character.\r\n\r\n"
            "Example:\r\n  OoTModelManager/Saria/Saria_Adult.zar\r\n  OoTModelManager/Saria/Saria_Child.zar\r\n"
            "  OoTModelManager/Saria/Saria_Voice.bcsar\r\n\r\n"
            "Voice packs that belong to no character go in the Voice folder.\r\n"
            "When you apply a voice to a character that has none, the app remembers it (in a\r\n"
            "uses.txt file) so that character keeps that voice, also when picked at random.\r\n\r\n"
            "Convert models and voice packs at https://jd-contreras.github.io/oot3d-zobj-import/\r\n";
        size_t len = 0;
        u8* old = File_Read(README_FILE, &len);
        if (!old || len != sizeof(text) - 1 || memcmp(old, text, len) != 0) {
            File_Write(README_FILE, (const u8*)text, sizeof(text) - 1);
        }
        free(old);
    }
    DIR* dir = opendir(LIBRARY_DIR);
    if (!dir) return;
    struct dirent* e;
    while ((e = readdir(dir)) != NULL) {
        char path[PATH_LEN];
        if (e->d_name[0] == '.' || snprintf(path, sizeof(path), LIBRARY_DIR "/%s", e->d_name) >= (int)sizeof(path)) continue;
        if (IsFolder(path, e)) {
            if (IsVoiceFolderName(e->d_name)) ScanVoiceFolder(path, NULL, 0);
            else ScanCharacterFolder(path, e->d_name);
        } else if (EndsWith(e->d_name, ".zip")) {
            ScanZip(path, e->d_name);
        } else {
            // A loose file is a one-piece character named after the file.
            const int kind = ClassifyFile(path);
            if (kind < 0) continue;
            char name[NAME_LEN];
            Tidy(name, e->d_name);
            const int character = AddCharacter(name);
            AddItem(character, path, "", e->d_name, File_Size(path), kind);
            SidecarUses(character, e->d_name);
        }
    }
    closedir(dir);

    // Something with a voice pack but no model (a voice-only zip or folder left outside the
    // voice folder) is a voice, not a character to pick as a set.
    for (int i = 0; i < gCharacterCount; i++) {
        Character* c = &gCharacters[i];
        if (c->item[KIND_ADULT] < 0 && c->item[KIND_CHILD] < 0) c->hidden = 1;
    }

    // Sort the characters by name; the items follow their character through the remap.
    int* remap = malloc((gCharacterCount ? gCharacterCount : 1) * sizeof(int));
    Character* before = malloc((gCharacterCount ? gCharacterCount : 1) * sizeof(Character));
    if (remap && before) {
        memcpy(before, gCharacters, gCharacterCount * sizeof(Character));
        qsort(gCharacters, gCharacterCount, sizeof(Character), CompareCharacters);
        for (int i = 0; i < gCharacterCount; i++) {
            for (int j = 0; j < gCharacterCount; j++) {
                if (memcmp(&before[i], &gCharacters[j], sizeof(Character)) == 0) remap[i] = j;
            }
        }
        for (int i = 0; i < gItemCount; i++) gItems[i].character = remap[gItems[i].character];
    }
    free(remap);
    free(before);

    // A character's only piece of a kind is shown by the character's name; when a folder holds
    // several of one kind, each also shows its file name.
    for (int i = 0; i < gItemCount; i++) {
        Item* it = &gItems[i];
        int sameKind = 0;
        for (int j = 0; j < gItemCount; j++) {
            sameKind += gItems[j].character == it->character && gItems[j].kind == it->kind;
        }
        char label[NAME_LEN];
        if (sameKind > 1) snprintf(label, sizeof(label), "%.28s: %.30s", gCharacters[it->character].name, it->label);
        else snprintf(label, sizeof(label), "%s", gCharacters[it->character].name);
        memcpy(it->label, label, sizeof(label));
    }
    ResolveUses();
}

static const char* const sAppliedKeys[KIND_COUNT] = { "applied_adult=", "applied_child=", "applied_voice=" };

void Settings_Load(void) {
    memset(&gSettings, 0, sizeof(gSettings));
    gSettings.buttons = 1;
    gSettings.random = RANDOM_SET;
    FILE* f = fopen(SETTINGS_FILE, "r");
    if (!f) return;
    char line[KEY_LEN + 16];
    while (fgets(line, sizeof(line), f)) {
        line[strcspn(line, "\r\n")] = '\0';
        for (int k = 0; k < KIND_COUNT; k++) {
            const size_t n = strlen(sKeys[k]);
            if (strncmp(line, sKeys[k], n) == 0) snprintf(gSettings.chosen[k], KEY_LEN, "%s", line + n);
            const size_t m = strlen(sAppliedKeys[k]);
            if (strncmp(line, sAppliedKeys[k], m) == 0) snprintf(gSettings.applied[k], KEY_LEN, "%s", line + m);
        }
        if (strncmp(line, "buttons=", 8) == 0) gSettings.buttons = line[8] != '0';
        if (strncmp(line, "link_voice=", 11) == 0) gSettings.linkVoice = line[11] == '1';
        for (int i = 0; i < 2; i++) {
            unsigned idx, size, offset, crc;
            if (sscanf(line, "voice_mark%u=%u,%u,%x", &idx, &size, &offset, &crc) == 4 && idx == (unsigned)i) {
                gSettings.voiceMark[i].size = size;
                gSettings.voiceMark[i].offset = offset;
                gSettings.voiceMark[i].crc = crc;
            }
        }
        if (strncmp(line, "secret=", 7) == 0) gSettings.secret = line[7] == '1';
        if (strncmp(line, "randomize=", 10) == 0) gSettings.random = (u8)(atoi(line + 10) & (RANDOM_SET | RANDOM_KINDS));
        if (strncmp(line, "region=", 7) == 0 && isdigit((unsigned char)line[7])) {
            gSettings.region = (u8)((line[7] - '0') % REGION_SETTING_COUNT);
        }
    }
    fclose(f);
}

void Settings_Save(void) {
    char text[KIND_COUNT * 2 * (KEY_LEN + 16) + 160];
    int n = 0;
    for (int k = 0; k < KIND_COUNT; k++) {
        n += snprintf(text + n, sizeof(text) - n, "%s%s\n", sKeys[k], gSettings.chosen[k]);
        n += snprintf(text + n, sizeof(text) - n, "%s%s\n", sAppliedKeys[k], gSettings.applied[k]);
    }
    n += snprintf(text + n, sizeof(text) - n, "randomize=%d\nsecret=%d\nregion=%d\nbuttons=%d\nlink_voice=%d\n", gSettings.random,
                  gSettings.secret, gSettings.region, gSettings.buttons, gSettings.linkVoice);
    for (int i = 0; i < 2; i++) {
        n += snprintf(text + n, sizeof(text) - n, "voice_mark%d=%u,%u,%08x\n", i, (unsigned)gSettings.voiceMark[i].size,
                      (unsigned)gSettings.voiceMark[i].offset, (unsigned)gSettings.voiceMark[i].crc);
    }
    File_Write(SETTINGS_FILE, (const u8*)text, (size_t)n);
}
