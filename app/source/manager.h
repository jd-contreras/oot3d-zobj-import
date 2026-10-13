// Everything the app does that is not drawing: files on the SD card, the randomizer seeds,
// the mod library and applying a choice to the game's mod folder.
#pragma once

#include <3ds.h>
#include <stddef.h>

#define PATH_LEN 256
#define NAME_LEN 64
#define MESSAGE_LEN 320

// ---- progress (apply.c) -----------------------------------------------------------------
// Slow work is split into steps, and the file functions report how far along a step is, so
// the screen can show a bar that keeps moving. The screen sets gProgressDraw; with it unset
// (the PC tests) nothing is drawn.
extern void (*gProgressDraw)(const char* what, float fraction);
void Progress_Begin(int steps);
void Progress_Step(const char* what);          // the next step starts
void Progress_Part(size_t done, size_t total); // how far the current step is

// ---- files.c ----------------------------------------------------------------------------
u8* File_Read(const char* path, size_t* len);
int File_Write(const char* path, const u8* data, size_t len); // via a temporary file next to it
int File_Copy(const char* from, const char* to);
int File_Exists(const char* path);
long File_Size(const char* path); // -1 if missing
void File_MakeParents(const char* path); // creates the folders leading to `path`
// Reads `len` bytes at `offset` into `out`. Returns 1 only if all of them were read.
int File_ReadAt(const char* path, long offset, u8* out, size_t len);

// ---- seed.c: the randomizer seeds in luma/titles ----------------------------------------
typedef enum {
    SEED_MISSING,     // no code.ips in the title folder
    SEED_READY,       // from a supported randomizer version, not patched yet
    SEED_PATCHED,     // already has Extra Buttons
    SEED_UNSUPPORTED, // from another randomizer version
    SEED_UNREADABLE,  // not a patch file, or it could not be read
} SeedState;

typedef struct {
    const char* name;    // region name
    const char* titleId; // its folder in luma/titles
    int region;
    SeedState state;
    int build;           // index into the patch table when READY or PATCHED
    u8 hasBackup;
    u8 patchedNow;       // patched in this run of the app
    u8 folderExists;
} Slot;

#define SLOT_COUNT 2
extern Slot gSlots[SLOT_COUNT];

void Seed_ScanAll(void);
const char* Seed_BuildName(const Slot* slot); // randomizer version of a READY / PATCHED seed
// Each writes a one-line result for the player into `msg`. Patch returns 1 if it patched.
// dropTunics: a custom model is in use, so the seed's Custom Tunic Colors must be off (see
// merge.h). Seed_Update redoes an already patched seed when that has changed since.
int Seed_Patch(Slot* slot, int dropTunics, char* msg);
void Seed_Update(Slot* slot, int dropTunics, char* msg);
void Seed_Undo(Slot* slot, char* msg);
void Seed_Path(const Slot* slot, const char* file, char* out); // out: PATH_LEN

// ---- library.c: sdmc:/OoTModelManager ---------------------------------------------------
#define LIBRARY_DIR "sdmc:/OoTModelManager"

typedef enum { KIND_ADULT, KIND_CHILD, KIND_VOICE, KIND_COUNT } Kind;
extern const char* const gKindNames[KIND_COUNT];

// One converted mod file: a file in the library, or a file inside a .zip in the library.
#define KEY_LEN (PATH_LEN + 168)
typedef struct {
    char label[NAME_LEN]; // shown in the lists
    char path[PATH_LEN];  // the file, or the zip it is in
    char entry[164];      // its path inside the zip, "" for a plain file
    char key[KEY_LEN];    // what the settings remember it by
    long size;
    Kind kind;
    int character;
} Item;

// The item's bytes in a newly allocated buffer (free() it), or NULL.
u8* Item_Read(const Item* item, size_t* len);

// A folder, a .zip or one loose file in the library: the pieces picked together as a set.
// A character may have a "uses" file with lines like "voice=Saria": that piece of its set is
// the library item shown under that name (two characters sharing one voice pack, without a
// second copy). The file is uses.txt in a character's folder, or <file name>.uses.txt next to
// a zip or a loose file. The app writes it when a voice is applied to a character without one.
typedef struct {
    char name[NAME_LEN];
    int item[KIND_COUNT];            // the item of each kind, or -1
    char uses[KIND_COUNT][NAME_LEN]; // name of the item a missing piece is borrowed from, or ""
    char usesPath[PATH_LEN];
    u8 borrowed[KIND_COUNT];
    u8 hidden; // a file in the voice folder: listed under Voice, but not a set of its own
} Character;

// Files in this folder of the library are voice packs on their own, not characters.
#define VOICE_FOLDER "Voice"

// Makes `name` (NULL: nothing) the piece of `kind` a character borrows, in its uses file.
// Returns 1 if the file was written.
int Library_SetUses(int character, Kind kind, const char* name);

#define MAX_ITEMS 256
#define MAX_CHARACTERS 128
extern Item gItems[MAX_ITEMS];
extern int gItemCount;
extern Character gCharacters[MAX_CHARACTERS];
extern int gCharacterCount;

void Library_Scan(void);

// What the player chose last, kept in the library folder.
typedef enum { REGION_AUTO, REGION_USA, REGION_EUR, REGION_SETTING_COUNT } RegionSetting;
// What the randomize button picks (Settings.random, a set of flags): one whole character, or
// any of the three kinds each on its own. "All" is the three kinds together.
#define RANDOM_SET 1
#define RANDOM_ADULT 2
#define RANDOM_CHILD 4
#define RANDOM_VOICE 8
#define RANDOM_KINDS (RANDOM_ADULT | RANDOM_CHILD | RANDOM_VOICE)
typedef enum { OPTION_SET, OPTION_ADULT, OPTION_CHILD, OPTION_VOICE, OPTION_ALL, OPTION_COUNT } RandomOption;

#define CHOICE_NONE "none" // chosen: the game's own (the mod file is removed)
typedef struct {
    // Per kind: the key of the chosen library item, CHOICE_NONE, or "" if never chosen (the
    // card is left as it is). `applied` is what Apply_Patch last put on the card.
    char chosen[KIND_COUNT][KEY_LEN];
    char applied[KIND_COUNT][KEY_LEN];
    u8 random;  // RANDOM_ flags: what the randomize button picks
    u8 secret;  // what it picked is not shown
    u8 region;  // RegionSetting
    u8 buttons; // Apply_Patch adds the Extra Buttons patch (off: removes it)
    // The voice was picked on its own (not as part of a set): Apply_Patch makes it the voice
    // of the chosen characters that have none of their own.
    u8 linkVoice;
    // The sound file as the app left it, per game folder: its size, and the place and checksum
    // of the start of Link's voice in it. Lets a start-up check tell, by reading only a little,
    // that the randomizer (or anything else) has replaced the file since.
    struct {
        u32 size, offset, crc;
    } voiceMark[2];
} Settings;
extern Settings gSettings;

void Settings_Load(void);
void Settings_Save(void);

// ---- apply.c ----------------------------------------------------------------------------
// Returns 1 if the slot's game folder is one mods are written to (per the region setting).
int Apply_UsesSlot(const Slot* slot);
// Choosing only records the choice; Apply_Patch is what changes the card.
void Apply_Choose(Kind kind, int item); // `item` < 0: the game's own
// A character's pieces. `whole`: kinds it doesn't have go back to the game's own; otherwise
// they are left as chosen before, so sets can be mixed.
void Apply_ChooseSet(int character, int whole);
// The randomize settings. A whole character and single kinds exclude each other: turning one
// on turns the other off.
int Apply_RandomOptionOn(RandomOption option);
void Apply_ToggleRandomOption(RandomOption option);
// Whether the randomize button picks this kind, and whether that pick is kept from view.
int Apply_Randomizes(Kind kind);
int Apply_Hidden(Kind kind);
// Picks at random per the settings. Like any choice it is only a selection until Apply_Patch.
// Returns 0 if nothing is turned on or the library has nothing to pick from.
int Apply_RandomizeNow(void);
int Apply_IsChosen(int item);
// Whether a choice (or the buttons setting, for a seed) is waiting for Apply_Patch.
int Apply_Pending(Kind kind);
int Apply_ButtonsPending(const Slot* slot);
int Apply_AnyPending(void);
// Checks what was applied against the card (call after Seed_ScanAll): a model or voice file
// that was deleted or replaced outside the app is no longer counted as applied, so the choice
// shows as waiting again.
void Apply_Verify(void);
// Adds or removes the Extra Buttons patch per the setting, and puts the chosen models and
// voice in the game's mod folder. Writes what happened for the player into `msg`. Returns
// how many things could not be done (0: everything worked).
int Apply_Patch(char* msg);
void Message_Add(char* msg, const char* fmt, ...) __attribute__((format(printf, 2, 3)));
