// PC test of the merge core: merges a seed with every bundled patch and writes the result,
// to compare against the OoT3D Model Importer's output for the same seed.
//   test_host <seed code.ips> <out.ips> [drop]      (run from the app folder, after gen_builds.py)
// drop: turn the seed's Custom Tunic Colors off, as when a custom model is used.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "source/builds.h"

static uint8_t* ReadFile(const char* path, size_t* len) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *len = (size_t)ftell(f);
    rewind(f);
    uint8_t* d = malloc(*len ? *len : 1);
    if (d && fread(d, 1, *len, f) != *len) {
        free(d);
        d = NULL;
    }
    fclose(f);
    return d;
}

static const char* const sNames[] = { "ok", "not an IPS patch", "another randomizer build", "already patched",
                                      "not a seed", "wrong region", "no memory" };

int main(int argc, char** argv) {
    if (argc != 3 && argc != 4) return 2;
    size_t seedLen, baseLen, outLen;
    uint8_t* seed = ReadFile(argv[1], &seedLen);
    if (!seed) return 2;
    int last = MERGE_OTHER_BUILD;
    for (int i = 0; i < BUILD_COUNT; i++) {
        char path[256];
        snprintf(path, sizeof(path), "romfs/%s", gBuilds[i].file + strlen("romfs:/"));
        uint8_t* base = ReadFile(path, &baseLen);
        if (!base) return 2;
        const MergeResult id = Merge_Identify(seed, seedLen, base, baseLen, &gBuilds[i]);
        if (id == MERGE_OK) {
            uint8_t* out;
            int tunics = 0;
            const MergeResult res = Merge_Apply(seed, seedLen, base, baseLen, &gBuilds[i], argc == 4, &tunics, &out, &outLen);
            printf("%s, %s: %s, %u bytes, custom tunics were %s\n", gBuilds[i].source, gBuilds[i].region ? "Europe" : "USA",
                   sNames[res], (unsigned)outLen, tunics ? "on" : "off");
            if (res == MERGE_OK) {
                FILE* f = fopen(argv[2], "wb");
                fwrite(out, 1, outLen, f);
                fclose(f);
                free(out);
            }
            return res;
        }
        if (id != MERGE_OTHER_BUILD) last = id;
        free(base);
    }
    printf("not merged: %s\n", sNames[last]);
    return last;
}
