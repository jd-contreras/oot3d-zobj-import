// PC test of the voice lift: puts the voice of <pack> into <target> and writes the result, to
// compare against the OoT3D Model Importer's tools (csar.rebuild / rebuild_warc).
//   test_voice <voice-pack bcsar> <target bcsar> <out bcsar>
#include <stdio.h>
#include <stdlib.h>

#include "source/voicelift.h"

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

static const char* const sNames[] = { "ok", "target already has this voice", "bad voice pack", "bad target",
                                      "no memory" };

int main(int argc, char** argv) {
    if (argc != 4) return 9;
    size_t packLen = 0, targetLen = 0, outLen = 0;
    uint8_t* pack = ReadFile(argv[1], &packLen);
    uint8_t* target = ReadFile(argv[2], &targetLen);
    if (!pack || !target) return 9;
    uint8_t* out = NULL;
    const LiftResult res = VoiceLift(pack, packLen, target, targetLen, &out, &outLen);
    printf("%s, %u bytes\n", sNames[res], (unsigned)outLen);
    if (res == LIFT_OK) {
        FILE* f = fopen(argv[3], "wb");
        fwrite(out, 1, outLen, f);
        fclose(f);
    }
    free(out);
    return res;
}
