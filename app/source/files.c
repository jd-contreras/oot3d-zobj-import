#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

#include "manager.h"

#define COPY_CHUNK 0x10000
#define WRITE_CHUNK 0x40000
#define TEMP_SUFFIX ".tmp"

u8* File_Read(const char* path, size_t* len) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    rewind(f);
    u8* data = size > 0 ? malloc((size_t)size) : NULL;
    if (data && fread(data, 1, (size_t)size, f) != (size_t)size) {
        free(data);
        data = NULL;
    }
    fclose(f);
    if (data) *len = (size_t)size;
    return data;
}

int File_Exists(const char* path) {
    FILE* f = fopen(path, "rb");
    if (f) fclose(f);
    return f != NULL;
}

long File_Size(const char* path) {
    FILE* f = fopen(path, "rb");
    if (!f) return -1;
    fseek(f, 0, SEEK_END);
    const long size = ftell(f);
    fclose(f);
    return size;
}

int File_ReadAt(const char* path, long offset, u8* out, size_t len) {
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    const int ok = fseek(f, offset, SEEK_SET) == 0 && fread(out, 1, len, f) == len;
    fclose(f);
    return ok;
}

void File_MakeParents(const char* path) {
    char dir[PATH_LEN];
    snprintf(dir, sizeof(dir), "%s", path);
    // Skip the device ("sdmc:/") and make each folder on the way down.
    char* p = strchr(dir, '/');
    for (p = p ? p + 1 : dir; (p = strchr(p, '/')) != NULL; p++) {
        *p = '\0';
        mkdir(dir, 0777);
        *p = '/';
    }
}

// The new file is written next to the old one first, so a failed write (a full card, for
// example) leaves the file that was there.
static int Finish(const char* path, const char* temp, int ok) {
    if (!ok) {
        remove(temp);
        return 0;
    }
    remove(path);
    return rename(temp, path) == 0;
}

int File_Write(const char* path, const u8* data, size_t len) {
    char temp[PATH_LEN + sizeof(TEMP_SUFFIX)];
    snprintf(temp, sizeof(temp), "%s" TEMP_SUFFIX, path);
    File_MakeParents(path);
    FILE* f = fopen(temp, "wb");
    if (!f) return 0;
    int ok = 1;
    for (size_t done = 0; ok && done < len;) { // in pieces, so progress can be shown
        const size_t n = len - done < WRITE_CHUNK ? len - done : WRITE_CHUNK;
        ok = fwrite(data + done, 1, n, f) == n;
        done += n;
        Progress_Part(done, len);
    }
    ok = fclose(f) == 0 && ok;
    return Finish(path, temp, ok);
}

int File_Copy(const char* from, const char* to) {
    char temp[PATH_LEN + sizeof(TEMP_SUFFIX)];
    snprintf(temp, sizeof(temp), "%s" TEMP_SUFFIX, to);
    File_MakeParents(to);
    FILE* in = fopen(from, "rb");
    if (!in) return 0;
    FILE* out = fopen(temp, "wb");
    u8* chunk = malloc(COPY_CHUNK);
    int ok = out != NULL && chunk != NULL;
    fseek(in, 0, SEEK_END);
    const size_t total = (size_t)ftell(in);
    rewind(in);
    size_t n, done = 0;
    while (ok && (n = fread(chunk, 1, COPY_CHUNK, in)) > 0) {
        ok = fwrite(chunk, 1, n, out) == n;
        done += n;
        Progress_Part(done, total);
    }
    ok = ok && !ferror(in);
    free(chunk);
    fclose(in);
    if (out) ok = fclose(out) == 0 && ok;
    return Finish(to, temp, ok);
}
