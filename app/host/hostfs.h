// PC test only (force-included with -include): sends the app's "sdmc:/" and "romfs:/" paths to
// folders named by the HOST_SD and HOST_ROMFS environment variables.
#pragma once

#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#endif

static inline const char* HostPath(const char* path, char* buf, size_t size) {
    if (strncmp(path, "sdmc:/", 6) == 0) snprintf(buf, size, "%s/%s", getenv("HOST_SD"), path + 6);
    else if (strncmp(path, "romfs:/", 7) == 0) snprintf(buf, size, "%s/%s", getenv("HOST_ROMFS"), path + 7);
    else snprintf(buf, size, "%s", path);
    const size_t n = strlen(buf); // "folder/" -> "folder"
    if (n && buf[n - 1] == '/') buf[n - 1] = '\0';
    return buf;
}

static inline FILE* HostFopen(const char* path, const char* mode) {
    char buf[600];
    return fopen(HostPath(path, buf, sizeof(buf)), mode);
}

static inline DIR* HostOpendir(const char* path) {
    char buf[600];
    return opendir(HostPath(path, buf, sizeof(buf)));
}

static inline int HostMkdir(const char* path) {
    char buf[600];
#ifdef _WIN32
    return _mkdir(HostPath(path, buf, sizeof(buf)));
#else
    return mkdir(HostPath(path, buf, sizeof(buf)), 0777);
#endif
}

static inline int HostRemove(const char* path) {
    char buf[600];
    return remove(HostPath(path, buf, sizeof(buf)));
}

static inline int HostRename(const char* from, const char* to) {
    char a[600], b[600];
    return rename(HostPath(from, a, sizeof(a)), HostPath(to, b, sizeof(b)));
}

static inline int HostIsDir(const char* path) {
    char buf[600];
    struct stat st;
    return stat(HostPath(path, buf, sizeof(buf)), &st) == 0 && S_ISDIR(st.st_mode);
}

#define fopen HostFopen
#define opendir HostOpendir
#define mkdir(path, mode) HostMkdir(path)
#define remove HostRemove
#define rename HostRename
