// Lifts Link's voice out of a voice-pack QueenSound.bcsar and puts it into another
// QueenSound.bcsar (the game's own, or the one the randomizer writes with shuffled music).
// Plain C with no 3DS calls, so it is also built and tested on a PC (test_host.c).
// Same method as the OoT3D Model Importer's tools/voice.py and tools/csar.py.
#pragma once

#include <stddef.h>
#include <stdint.h>

typedef enum {
    LIFT_OK = 0,
    LIFT_SAME,       // the target already has this voice
    LIFT_BAD_PACK,   // the voice pack is not a QueenSound.bcsar this can read
    LIFT_BAD_TARGET, // the target is not a QueenSound.bcsar this can read
    LIFT_NO_MEMORY,
} LiftResult;

// Returns 1 if `data` starts like a sound archive.
int VoiceLift_IsArchive(const uint8_t* data, size_t len);

// Where Link's voice starts in a sound archive (the offset of his first voice wave). Returns 1
// if the archive could be read.
int VoiceLift_Locate(const uint8_t* archive, size_t len, size_t* offset);

// Writes `target` with Link's voice taken from `pack` to a newly allocated buffer (free() it).
LiftResult VoiceLift(const uint8_t* pack, size_t packLen, const uint8_t* target, size_t targetLen, uint8_t** out,
                     size_t* outLen);
