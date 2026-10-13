// PC test of the app's file logic (library scan, choosing, and what "Apply patch" does) against
// a fake SD card. Build:
//   gcc -std=gnu11 -DHOST_TEST -include host/hostfs.h -Ihost test_manager.c source/files.c
//       source/seed.c source/library.c source/apply.c source/merge.c source/voicelift.c source/unzip.c
// The folders come from the HOST_SD and HOST_ROMFS environment variables. Each command prints
// what the app would show, so a script can set up files, run commands and compare the results.
//   test_manager scan | apply | set <character> | pick <adult|child|voice> <label|none>
//                | roll | random <off|set|adult|child|voice|all> | toggle <set|adult|child|voice|all>
//                | secret <0|1> | buttons <0|1>
// Only "apply" changes anything outside the settings file, as in the app.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "source/manager.h"

static const char* const sStates[] = { "no seed", "ready", "patched", "unsupported", "unreadable" };

static void Show(const char* msg) {
    for (int i = 0; i < SLOT_COUNT; i++) {
        printf("seed %s: %s %s\n", gSlots[i].name, sStates[gSlots[i].state], Seed_BuildName(&gSlots[i]));
    }
    for (int k = 0; k < KIND_COUNT; k++) {
        printf("chosen %s: %s%s%s\n", gKindNames[k], gSettings.chosen[k], Apply_Hidden((Kind)k) ? "  (hidden)" : "",
               Apply_Pending((Kind)k) ? "  (pending)" : "");
    }
    printf("random: %d  secret: %d  buttons: %d  anything pending: %d\n%s", gSettings.random, gSettings.secret,
           gSettings.buttons, Apply_AnyPending(), msg);
}

int main(int argc, char** argv) {
    char msg[MESSAGE_LEN] = "";
    if (argc < 2) return 2;
    srand((unsigned)time(NULL) ^ ((unsigned)getpid() << 8)); // the app seeds from the system tick
    Library_Scan();
    Settings_Load();
    Seed_ScanAll();
    Apply_Verify();
    if (!strcmp(argv[1], "scan")) {
        for (int c = 0; c < gCharacterCount; c++) {
            printf("character %s:%s", gCharacters[c].name, gCharacters[c].hidden ? " (voice folder)" : "");
            for (int k = 0; k < KIND_COUNT; k++) {
                printf(" %s=%d%s", gKindNames[k], gCharacters[c].item[k], gCharacters[c].borrowed[k] ? "(borrowed)" : "");
            }
            printf("\n");
        }
        for (int i = 0; i < gItemCount; i++) {
            printf("item %d: [%s] %s <- %s\n", i, gKindNames[gItems[i].kind], gItems[i].label, gItems[i].path);
        }
    } else if (!strcmp(argv[1], "apply")) {
        printf("problems: %d\n", Apply_Patch(msg));
    } else if (!strcmp(argv[1], "random") && argc > 2) { // off, or turn on only: set | adult | child | voice | all
        static const char* const options[OPTION_COUNT] = { "set", "adult", "child", "voice", "all" };
        gSettings.random = 0;
        Settings_Save();
        for (int o = 0; o < OPTION_COUNT; o++) {
            if (!strcmp(argv[2], options[o])) Apply_ToggleRandomOption((RandomOption)o);
        }
    } else if (!strcmp(argv[1], "toggle") && argc > 2) { // flip one randomize setting, as its row does
        static const char* const options[OPTION_COUNT] = { "set", "adult", "child", "voice", "all" };
        for (int o = 0; o < OPTION_COUNT; o++) {
            if (!strcmp(argv[2], options[o])) Apply_ToggleRandomOption((RandomOption)o);
        }
    } else if (!strcmp(argv[1], "roll")) { // the randomize button
        printf("rolled: %d\n", Apply_RandomizeNow());
    } else if (!strcmp(argv[1], "set") && argc > 2) {
        for (int c = 0; c < gCharacterCount; c++) {
            if (!strcmp(gCharacters[c].name, argv[2])) Apply_ChooseSet(c, 0);
        }
    } else if (!strcmp(argv[1], "pick") && argc > 3) {
        for (int k = 0; k < KIND_COUNT; k++) {
            if (strcasecmp(gKindNames[k], argv[2])) continue;
            int item = -1;
            for (int i = 0; i < gItemCount; i++) {
                if (gItems[i].kind == (Kind)k && !strcmp(gItems[i].label, argv[3])) item = i;
            }
            if (item >= 0 || !strcmp(argv[3], "none")) Apply_Choose((Kind)k, item);
        }
    } else if (!strcmp(argv[1], "secret") && argc > 2) {
        gSettings.secret = argv[2][0] == '1';
        Settings_Save();
    } else if (!strcmp(argv[1], "buttons") && argc > 2) {
        gSettings.buttons = argv[2][0] == '1';
        Settings_Save();
    }
    Seed_ScanAll();
    Show(msg);
    return 0;
}
