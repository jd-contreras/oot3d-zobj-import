// OoT Model Manager: on the console, adds the Extra Buttons patch to an OoT3D Randomizer seed
// and switches between converted character models and voice packs kept in
// sdmc:/OoTModelManager. This file is the two screens; the work is in manager.h's modules.
// Choosing only records what is wanted; "Apply patch" is what changes the card.
#include <3ds.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "manager.h"
#include "ui.h"

#define APP_NAME "OoT Model Manager"
#define APP_VERSION "2.6"

typedef enum { SCREEN_HOME, SCREEN_LIST, SCREEN_RANDOM, SCREEN_DONE } Screen;

// The list screen's tabs: whole characters, then one tab per kind of file.
typedef enum { TAB_SETS, TAB_ADULT, TAB_CHILD, TAB_VOICE, TAB_COUNT } Tab;
static const char* const sTabNames[TAB_COUNT] = { "Sets", "Adult", "Child", "Voice" };

// The home menu, top to bottom.
enum { HOME_CHOOSE, HOME_RANDOM, HOME_RANDOM_SETTINGS, HOME_BUTTONS, HOME_REGION, HOME_APPLY, HOME_COUNT };
static const char* const sRegionNames[REGION_SETTING_COUNT] = { "Auto", "USA", "Europe" };

// The randomize settings menu: the five things to randomize, then hiding the picks.
enum { RANDOM_ROW_SECRET = OPTION_COUNT, RANDOM_ROW_COUNT };
static const char* const sRandomLabels[RANDOM_ROW_COUNT] = { "Set", "Adult", "Child", "Voice", "All", "Secret random" };
static int sRandomCursor = 0;

#define HOME_BUTTON_H 34.0f
#define HOME_BUTTON_STEP 38.0f
#define TAB_H 26.0f
#define ROW_TOP 30.0f
#define ROW_H 23.0f
#define ROWS_VISIBLE 8
#define ENTRY_NONE (-1) // a kind tab's first row: back to the game's own

static Screen sScreen = SCREEN_HOME;
static int sHomeCursor = 0;
static Tab sTab = TAB_SETS;
static int sCursor[TAB_COUNT];
static int sScroll[TAB_COUNT];
static char sMessage[MESSAGE_LEN] = "";
static int sQuit = 0;
static int sProblems = 0; // from the last Apply patch, for the completion screen

// ---- the list screen's rows ---------------------------------------------------------------

// Rows of the current tab. A sets row is a character index; a kind row is an item index or
// ENTRY_NONE.
static int sRows[MAX_ITEMS + 1];
static int sRowCount;

static void BuildRows(void) {
    sRowCount = 0;
    if (sTab == TAB_SETS) {
        for (int i = 0; i < gCharacterCount; i++) {
            if (!gCharacters[i].hidden) sRows[sRowCount++] = i;
        }
    } else {
        const Kind kind = (Kind)(sTab - TAB_ADULT);
        sRows[sRowCount++] = ENTRY_NONE;
        for (int c = 0; c < gCharacterCount; c++) {
            for (int i = 0; i < gItemCount; i++) {
                if (gItems[i].character == c && gItems[i].kind == kind) sRows[sRowCount++] = i;
            }
        }
    }
    if (sCursor[sTab] >= sRowCount) sCursor[sTab] = sRowCount ? sRowCount - 1 : 0;
    if (sScroll[sTab] > sCursor[sTab]) sScroll[sTab] = sCursor[sTab];
    if (sScroll[sTab] < sCursor[sTab] - (ROWS_VISIBLE - 1)) sScroll[sTab] = sCursor[sTab] - (ROWS_VISIBLE - 1);
}

// Characters that are sets (the voice folder's files are not).
static int SetCount(void) {
    int n = 0;
    for (int i = 0; i < gCharacterCount; i++) n += !gCharacters[i].hidden;
    return n;
}

// Whether every piece a character has is the one chosen.
static int SetChosen(const Character* c) {
    int pieces = 0;
    for (int k = 0; k < KIND_COUNT; k++) {
        if (c->item[k] < 0) continue;
        if (!Apply_IsChosen(c->item[k])) return 0;
        pieces++;
    }
    return pieces > 0;
}

static void ChooseRow(int row) {
    sMessage[0] = '\0';
    if (sTab == TAB_SETS) Apply_ChooseSet(sRows[row], 0);
    else Apply_Choose((Kind)(sTab - TAB_ADULT), sRows[row]);
}

// What the highlighted option does, shown at the bottom of the top screen.
static const char* Description(void) {
    static char text[MESSAGE_LEN];
    if (sScreen == SCREEN_HOME) {
        switch (sHomeCursor) {
            case HOME_CHOOSE:
                if (!SetCount()) {
                    return "No characters yet. Put the importer's zips, or folders of converted files, in the "
                           "OoTModelManager folder at the top of the SD card, one per character.";
                }
                return "Pick a whole character, or mix an adult model, a child model and a voice.";
            case HOME_RANDOM:
                return "Picks at random, per the randomize settings. It is only selected: Apply patch uses it.";
            case HOME_RANDOM_SETTINGS:
                return "What the randomize button picks, and whether its picks are hidden.";
            case HOME_BUTTONS:
                return "On: Apply patch adds ZL / ZR and D-pad item buttons to your randomizer seed.\n"
                       "Off: Apply patch removes them.";
            case HOME_REGION:
                return "The game folder models and voice go to. Auto: the OoT3D folders found in luma/titles.";
            default:
                return "Writes your selection to the game: buttons, models and voice. Use after every new seed.";
        }
    }
    if (sScreen == SCREEN_RANDOM) {
        static const char* const what[RANDOM_ROW_COUNT] = {
            "Randomize picks one whole character. Turns the single kinds off.",
            "Randomize picks an adult model. The other kinds stay as selected unless they are on too.",
            "Randomize picks a child model. The other kinds stay as selected unless they are on too.",
            "Randomize picks a voice. The other kinds stay as selected unless they are on too.",
            "Adult, Child and Voice together: each picked on its own, so they can be mixed.",
            "On: what Randomize picks is not shown.",
        };
        return what[sRandomCursor];
    }
    if (!sRowCount) return "";
    const int row = sRows[sCursor[sTab]];
    if (sTab == TAB_SETS) {
        const Character* c = &gCharacters[row];
        int n = snprintf(text, sizeof(text), "Selects %s:", c->name);
        for (int k = 0; k < KIND_COUNT; k++) {
            if (c->item[k] < 0) continue;
            n += snprintf(text + n, sizeof(text) - n, " %s", k == KIND_ADULT ? "adult model," : k == KIND_CHILD ? "child model," : "voice,");
            if (c->borrowed[k]) n += snprintf(text + n - 1, sizeof(text) - n + 1, " (%s),", c->uses[k]) - 1;
        }
        text[n - 1] = '.';
        return text;
    }
    static const char* const what[KIND_COUNT] = { "adult model", "child model", "voice" };
    const char* kind = what[sTab - TAB_ADULT];
    if (row == ENTRY_NONE) snprintf(text, sizeof(text), "Removes the custom %s: the game's own is used.", kind);
    else if (sTab == TAB_VOICE) {
        snprintf(text, sizeof(text), "Selects this voice only. A selected character without a voice keeps it from then on.");
    } else snprintf(text, sizeof(text), "Selects this %s only.", kind);
    return text;
}

// ---- drawing ------------------------------------------------------------------------------

// What is chosen for a kind, as shown to the player. `dim`: it is not a library item.
static const char* ChosenName(Kind kind, int* dim) {
    const char* choice = gSettings.chosen[kind];
    *dim = 0;
    if (Apply_Hidden(kind)) return "???";
    for (int i = 0; i < gItemCount; i++) {
        if (strcmp(gItems[i].key, choice) == 0) return gItems[i].label;
    }
    *dim = 1;
    if (!choice[0]) return "Unchanged";
    return strcmp(choice, CHOICE_NONE) == 0 ? "The game's own" : "(file no longer in the folder)";
}

static void DrawTop(void) {
    const int done = sScreen == SCREEN_DONE;
    ui_top();
    ui_rect(0, 0, TOP_W, 30, CLR_HEADER);
    if (!done) ui_text(12, 5, 0.65f, CLR_TEXT, APP_NAME);
    else if (sProblems) ui_text(12, 5, 0.65f, CLR_WARN, "Finished, with problems");
    else ui_text(12, 5, 0.65f, CLR_TEXT, "Patch complete");
    ui_text_right(TOP_W - 12, 9, 0.45f, CLR_DIM, "v" APP_VERSION);

    ui_rect(8, 36, TOP_W - 16, 74, CLR_PANEL);
    ui_text(16, 39, 0.45f, CLR_ACCENT, done ? "Now in the game" : "Selected");
    for (int k = 0; k < KIND_COUNT; k++) {
        const float y = 54 + k * 18.0f;
        int dim;
        const char* name = ChosenName((Kind)k, &dim);
        const int pending = Apply_Pending((Kind)k) && !Apply_Hidden((Kind)k);
        ui_text(16, y, 0.5f, CLR_DIM, "%s", gKindNames[k]);
        ui_text_fit(76, y, 0.5f, dim ? CLR_DIM : CLR_TEXT, TOP_W - (pending ? 200 : 100), name);
        if (pending) ui_text_right(TOP_W - 16, y + 1, 0.42f, CLR_WARN, "not applied yet");
    }

    ui_rect(8, 114, TOP_W - 16, 58, CLR_PANEL);
    ui_text(16, 117, 0.45f, CLR_ACCENT, "Randomizer seed");
    int shown = 0;
    for (int i = 0; i < SLOT_COUNT; i++) {
        const Slot* s = &gSlots[i];
        if (s->state == SEED_MISSING) continue;
        const float y = 132 + shown++ * 18.0f;
        ui_text(16, y, 0.5f, CLR_DIM, "%s", s->name);
        switch (s->state) {
            case SEED_READY:
                if (gSettings.buttons) ui_text(76, y, 0.5f, CLR_WARN, "new seed: buttons not applied yet");
                else ui_text(76, y, 0.5f, CLR_DIM, "no Extra Buttons");
                break;
            case SEED_PATCHED:
                if (Apply_ButtonsPending(s)) ui_text(76, y, 0.5f, CLR_WARN, "buttons not removed yet");
                else ui_text(76, y, 0.5f, CLR_GOOD, "has Extra Buttons");
                break;
            case SEED_UNSUPPORTED:
                ui_text(76, y, 0.5f, CLR_ERR, "randomizer version not supported");
                break;
            default:
                ui_text(76, y, 0.5f, CLR_ERR, "code.ips could not be read");
                break;
        }
        if (s->build >= 0) ui_text_right(TOP_W - 16, y + 1, 0.4f, CLR_DIM, "%s", Seed_BuildName(s) + sizeof("OoT3D ") - 1);
    }
    if (!shown) ui_text(16, 132, 0.5f, CLR_DIM, "No seed found in luma/titles.");

    if (sMessage[0]) ui_text_wrap(12, 178, 0.45f, CLR_TEXT, TOP_W - 24, sMessage);
    else if (!done) ui_text_wrap(12, 178, 0.45f, CLR_DIM, TOP_W - 24, Description());
}

// After Apply patch: what to do next. The top screen shows what is now in the game.
static void DrawDone(void) {
    ui_bottom();
    // One box: the result, then what to press next.
    ui_rect(8, 8, BOTTOM_W - 16, SCREEN_H - 16, CLR_PANEL);
    if (sProblems) {
        ui_text(18, 20, 0.6f, CLR_WARN, "Not everything was applied.");
        ui_text_wrap(18, 52, 0.5f, CLR_TEXT, BOTTOM_W - 36, "The top screen says what went wrong. Fix it and choose Apply patch again.");
    } else {
        ui_text(18, 20, 0.6f, CLR_GOOD, "All done.");
        ui_text_wrap(18, 52, 0.5f, CLR_TEXT, BOTTOM_W - 36, "You can exit the app and start your game.");
    }
    ui_text(18, 130, 0.5f, CLR_DIM, "Press START or HOME to exit the app");
    ui_text(18, 152, 0.5f, CLR_DIM, "Press any button to go back to the menu");
}

static void HomeButton(int index, ui_box* box) {
    box->x = 8;
    box->y = 6 + index * HOME_BUTTON_STEP;
    box->w = BOTTOM_W - 16;
    box->h = HOME_BUTTON_H;
}

static void OnOff(float right, float y, int on) {
    ui_text_right(right, y, 0.55f, on ? CLR_GOOD : CLR_DIM, on ? "On" : "Off");
}

static void DrawHome(void) {
    static const char* const labels[HOME_COUNT] = {
        [HOME_CHOOSE] = "Choose models and voice",       [HOME_RANDOM] = "Press A to randomize",
        [HOME_RANDOM_SETTINGS] = "Randomize settings", [HOME_BUTTONS] = "Apply extra buttons",
        [HOME_REGION] = "Game region",                   [HOME_APPLY] = "Apply patch",
    };
    const int pending = Apply_AnyPending();
    ui_bottom();
    for (int i = 0; i < HOME_COUNT; i++) {
        ui_box b;
        HomeButton(i, &b);
        ui_rect(b.x, b.y, b.w, b.h, i == sHomeCursor ? CLR_SEL : CLR_BTN);
        ui_text(b.x + 10, b.y + 8, 0.55f, i == HOME_APPLY && pending ? CLR_ACCENT : CLR_TEXT, "%s", labels[i]);
        const float right = b.x + b.w - 10;
        if (i == HOME_CHOOSE) ui_text_right(right, b.y + 11, 0.4f, CLR_DIM, "%d characters", SetCount());
        else if (i == HOME_RANDOM_SETTINGS) {
            char on[40] = "";
            for (int o = 0; o < OPTION_ALL; o++) {
                if (!Apply_RandomOptionOn((RandomOption)o)) continue;
                snprintf(on + strlen(on), sizeof(on) - strlen(on), "%s%s", on[0] ? ", " : "", sRandomLabels[o]);
            }
            ui_text_right(right, b.y + 11, 0.4f, CLR_DIM, "%s%s", on[0] ? on : "nothing on", gSettings.secret ? ", secret" : "");
        }
        else if (i == HOME_BUTTONS) {
            // Once the seed has the buttons, say so instead of just "On".
            int patched = 0;
            for (int s = 0; s < SLOT_COUNT; s++) patched |= gSlots[s].state == SEED_PATCHED;
            if (gSettings.buttons && patched) ui_text_right(right, b.y + 8, 0.55f, CLR_GOOD, "APPLIED");
            else OnOff(right, b.y + 8, gSettings.buttons);
        }
        else if (i == HOME_REGION) ui_text_right(right, b.y + 8, 0.55f, CLR_DIM, "%s", sRegionNames[gSettings.region]);
        else if (i == HOME_APPLY && pending) ui_text_right(right, b.y + 11, 0.4f, CLR_ACCENT, "changes waiting");
        // The randomize button has no note of its own: the settings row below says what is on.
    }
}

static void DrawRandomSettings(void) {
    ui_bottom();
    for (int i = 0; i < RANDOM_ROW_COUNT; i++) {
        ui_box b;
        HomeButton(i, &b);
        ui_rect(b.x, b.y, b.w, b.h, i == sRandomCursor ? CLR_SEL : CLR_BTN);
        ui_text(b.x + 10, b.y + 8, 0.55f, CLR_TEXT, "%s", sRandomLabels[i]);
        OnOff(b.x + b.w - 10, b.y + 8, i == RANDOM_ROW_SECRET ? gSettings.secret : Apply_RandomOptionOn((RandomOption)i));
    }
}

static void DrawList(void) {
    ui_bottom();
    const float tabW = BOTTOM_W / (float)TAB_COUNT;
    for (int t = 0; t < TAB_COUNT; t++) {
        ui_rect(t * tabW, 0, tabW - 1, TAB_H, t == (int)sTab ? CLR_SEL : CLR_BTN);
        ui_text_center(t * tabW + tabW / 2, 5, 0.5f, t == (int)sTab ? CLR_TEXT : CLR_DIM, "%s", sTabNames[t]);
    }
    if (!sRowCount) ui_text(12, ROW_TOP + 6, 0.5f, CLR_DIM, "Nothing here yet.");
    for (int v = 0; v < ROWS_VISIBLE && sScroll[sTab] + v < sRowCount; v++) {
        const int row = sScroll[sTab] + v;
        const float y = ROW_TOP + v * ROW_H;
        if (row == sCursor[sTab]) ui_rect(4, y, BOTTOM_W - 8, ROW_H - 2, CLR_SEL);
        int chosen = 0;
        char note[32] = "";
        const char* label;
        if (sTab == TAB_SETS) {
            const Character* c = &gCharacters[sRows[row]];
            label = c->name;
            chosen = SetChosen(c);
            snprintf(note, sizeof(note), "%s%s%s", c->item[KIND_ADULT] >= 0 ? "Adult " : "",
                     c->item[KIND_CHILD] >= 0 ? "Child " : "", c->item[KIND_VOICE] >= 0 ? "Voice" : "");
        } else if (sRows[row] == ENTRY_NONE) {
            label = "None (the game's own)";
            chosen = strcmp(gSettings.chosen[sTab - TAB_ADULT], CHOICE_NONE) == 0;
        } else {
            label = gItems[sRows[row]].label;
            chosen = Apply_IsChosen(sRows[row]);
        }
        // A secret random pick is not given away by the "selected" mark either.
        if (sTab == TAB_SETS ? (gSettings.secret && gSettings.random) : Apply_Hidden((Kind)(sTab - TAB_ADULT))) chosen = 0;
        if (chosen) snprintf(note, sizeof(note), "selected");
        ui_text_fit(10, y + 3, 0.5f, CLR_TEXT, BOTTOM_W - 120, label);
        ui_text_right(BOTTOM_W - 10, y + 5, 0.4f, chosen ? CLR_GOOD : CLR_DIM, "%s", note);
    }
    if (sRowCount > ROWS_VISIBLE) {
        ui_text_right(BOTTOM_W - 8, 222, 0.4f, CLR_DIM, "%d / %d", sCursor[sTab] + 1, sRowCount);
    }
    ui_text(8, 222, 0.4f, CLR_DIM, "A: select   B: back   L / R: tab");
}

// ---- input --------------------------------------------------------------------------------

static void HomeAction(int action) {
    sMessage[0] = '\0';
    switch (action) {
        case HOME_CHOOSE:
            sScreen = SCREEN_LIST;
            BuildRows();
            break;
        case HOME_RANDOM:
            if (!gSettings.random) Message_Add(sMessage, "Nothing to randomize: turn something on in Randomize settings.");
            else if (!Apply_RandomizeNow()) Message_Add(sMessage, "Nothing to pick from: add characters to the OoTModelManager folder.");
            break;
        case HOME_RANDOM_SETTINGS:
            sScreen = SCREEN_RANDOM;
            break;
        case HOME_BUTTONS:
            gSettings.buttons = !gSettings.buttons;
            Settings_Save();
            break;
        case HOME_REGION:
            gSettings.region = (u8)((gSettings.region + 1) % REGION_SETTING_COUNT);
            Settings_Save();
            break;
        case HOME_APPLY:
            ui_progress(APP_NAME, "Applying your choices", 0);
            sProblems = Apply_Patch(sMessage);
            sScreen = SCREEN_DONE;
            break;
    }
}

static void UpdateHome(u32 down, const touchPosition* touch) {
    if (down & (KEY_DOWN | KEY_UP)) sMessage[0] = '\0'; // back to the option's description
    if (down & KEY_DOWN) sHomeCursor = (sHomeCursor + 1) % HOME_COUNT;
    if (down & KEY_UP) sHomeCursor = (sHomeCursor + HOME_COUNT - 1) % HOME_COUNT;
    if (down & KEY_TOUCH) {
        for (int i = 0; i < HOME_COUNT; i++) {
            ui_box b;
            HomeButton(i, &b);
            if (ui_hit(&b, touch)) {
                // The first tap highlights an option (and shows what it does); a tap on the
                // highlighted option uses it.
                if (i == sHomeCursor) down |= KEY_A;
                else sMessage[0] = '\0';
                sHomeCursor = i;
            }
        }
    }
    if (down & KEY_A) HomeAction(sHomeCursor);
    if (down & KEY_START) sQuit = 1;
}

static void UpdateRandomSettings(u32 down, const touchPosition* touch) {
    if (down & KEY_DOWN) sRandomCursor = (sRandomCursor + 1) % RANDOM_ROW_COUNT;
    if (down & KEY_UP) sRandomCursor = (sRandomCursor + RANDOM_ROW_COUNT - 1) % RANDOM_ROW_COUNT;
    if (down & KEY_TOUCH) {
        for (int i = 0; i < RANDOM_ROW_COUNT; i++) {
            ui_box b;
            HomeButton(i, &b);
            if (ui_hit(&b, touch)) { // toggles are harmless, so a tap flips one straight away
                sRandomCursor = i;
                down |= KEY_A;
            }
        }
    }
    if (down & KEY_A) {
        if (sRandomCursor == RANDOM_ROW_SECRET) {
            gSettings.secret = !gSettings.secret;
            Settings_Save();
        } else {
            Apply_ToggleRandomOption((RandomOption)sRandomCursor);
        }
    }
    if (down & KEY_B) sScreen = SCREEN_HOME;
    if (down & KEY_START) sQuit = 1;
}

// The completion screen: START exits, anything else goes back to the menu.
static void UpdateDone(u32 down) {
    if (down & KEY_START) {
        sQuit = 1;
    } else if (down) {
        sMessage[0] = '\0';
        sScreen = SCREEN_HOME;
    }
}

static void MoveCursor(int delta) {
    if (!sRowCount) return;
    int c = sCursor[sTab] + delta;
    if (delta == 1 && c >= sRowCount) c = 0;          // single steps wrap around
    else if (delta == -1 && c < 0) c = sRowCount - 1;
    if (c < 0) c = 0;
    if (c >= sRowCount) c = sRowCount - 1;
    sCursor[sTab] = c;
    BuildRows();
}

static void UpdateList(u32 down, const touchPosition* touch) {
    if (down & (KEY_R | KEY_L)) {
        sTab = (Tab)((sTab + ((down & KEY_R) ? 1 : TAB_COUNT - 1)) % TAB_COUNT);
        BuildRows();
    }
    if (down & KEY_DOWN) MoveCursor(1);
    if (down & KEY_UP) MoveCursor(-1);
    if (down & KEY_RIGHT) MoveCursor(ROWS_VISIBLE);
    if (down & KEY_LEFT) MoveCursor(-ROWS_VISIBLE);
    if (down & KEY_TOUCH) {
        if (touch->py < TAB_H) {
            sTab = (Tab)(touch->px * TAB_COUNT / BOTTOM_W);
            BuildRows();
        } else if (touch->py >= ROW_TOP && touch->py < ROW_TOP + ROWS_VISIBLE * ROW_H) {
            const int row = sScroll[sTab] + (int)((touch->py - ROW_TOP) / ROW_H);
            if (row < sRowCount) { // a tap selects: nothing is written until "Apply patch"
                sCursor[sTab] = row;
                down |= KEY_A;
            }
        }
    }
    if ((down & KEY_A) && sRowCount) ChooseRow(sCursor[sTab]);
    if (down & KEY_B) sScreen = SCREEN_HOME;
    if (down & KEY_START) sQuit = 1;
}

static void DrawProgress(const char* what, float fraction) {
    ui_progress(APP_NAME, what, fraction);
}

int main(void) {
    ui_init();
    gProgressDraw = DrawProgress;
    srand((unsigned)svcGetSystemTick());
    ui_busy(APP_NAME, "Reading the SD card...");
    if (R_FAILED(romfsInit())) Message_Add(sMessage, "The app's own files could not be opened.");
    Library_Scan();
    Settings_Load();
    Seed_ScanAll();
    Apply_Verify();

    while (aptMainLoop() && !sQuit) {
        hidScanInput();
        const u32 down = hidKeysDown();
        touchPosition touch;
        hidTouchRead(&touch);
        if (sScreen == SCREEN_HOME) UpdateHome(down, &touch);
        else if (sScreen == SCREEN_DONE) UpdateDone(down);
        else if (sScreen == SCREEN_RANDOM) UpdateRandomSettings(down, &touch);
        else UpdateList(down, &touch);

        ui_begin();
        DrawTop();
        if (sScreen == SCREEN_HOME) DrawHome();
        else if (sScreen == SCREEN_DONE) DrawDone();
        else if (sScreen == SCREEN_RANDOM) DrawRandomSettings();
        else DrawList();
        ui_end();
    }

    romfsExit();
    ui_exit();
    return 0;
}
