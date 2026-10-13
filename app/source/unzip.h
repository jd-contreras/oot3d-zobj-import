// Reads files out of a .zip (stored or deflated entries, no ZIP64, no encryption), so a zip
// made by the OoT3D Model Importer can sit in the library as it is.
// Plain C with no 3DS calls, so it is also built and tested on a PC (test_manager.c).
#pragma once

#include <stddef.h>
#include <stdint.h>

#define ZIP_NAME_LEN 160

typedef struct {
    char name[ZIP_NAME_LEN]; // path inside the zip
    uint32_t method;         // 0 stored, 8 deflated
    uint32_t packedSize;
    uint32_t size;
    uint32_t crc;
    uint32_t headerOffset;   // of the entry's local header
} ZipEntry;

// The checksum zips use (CRC-32).
uint32_t Zip_Crc32(const uint8_t* data, size_t len);

// Lists up to `max` entries of the zip at `path`. Returns the count, or -1 if it is not a zip
// this can read. Entries with names too long for ZipEntry are skipped.
int Zip_List(const char* path, ZipEntry* out, int max);

// The first `want` bytes of an entry (all of it when `want` is 0 or more than its size), in a
// newly allocated buffer (free() it); `len` receives how many. A whole entry is checked against
// the zip's checksum. Returns NULL on any error.
uint8_t* Zip_Read(const char* path, const ZipEntry* entry, size_t want, size_t* len);
