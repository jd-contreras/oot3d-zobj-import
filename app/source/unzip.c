#include "unzip.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define EOCD_SIZE 22         // end of central directory record, without its comment
#define EOCD_SEARCH 0x10016  // the record plus the longest possible comment
#define CENTRAL_SIZE 46
#define LOCAL_SIZE 30
#define METHOD_STORED 0
#define METHOD_DEFLATED 8

static uint32_t Le16(const uint8_t* p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8);
}

static uint32_t Le32(const uint8_t* p) {
    return Le16(p) | (Le16(p + 2) << 16);
}

// ---- inflate ------------------------------------------------------------------------------
// A small decoder for deflate data (RFC 1951) that writes into a buffer of known size. The
// output so far is the history window, so no separate window is kept. Decoding stops cleanly
// when the buffer is full, which is how the first bytes of a large entry are read.

#define MAX_BITS 15
#define MAX_LITERAL_CODES 286
#define MAX_DISTANCE_CODES 30
#define FIXED_LITERAL_CODES 288

typedef struct {
    const uint8_t* in;
    size_t inLen, inPos;
    uint32_t bitBuf;
    int bitCount;
    uint8_t* out;
    size_t outLen, outPos;
    int error; // ran out of input, or the data is not valid deflate
} Inflater;

typedef struct {
    uint16_t count[MAX_BITS + 1]; // number of codes of each length
    uint16_t symbol[FIXED_LITERAL_CODES];
} Huffman;

static uint32_t Bits(Inflater* s, int need) {
    uint32_t val = s->bitBuf;
    while (s->bitCount < need) {
        if (s->inPos >= s->inLen) {
            s->error = 1;
            return 0;
        }
        val |= (uint32_t)s->in[s->inPos++] << s->bitCount;
        s->bitCount += 8;
    }
    s->bitBuf = need < 32 ? val >> need : 0;
    s->bitCount -= need;
    return need < 32 ? val & ((1u << need) - 1) : val;
}

// Decodes one symbol, reading a bit at a time (canonical Huffman codes, shortest first).
static int Decode(Inflater* s, const Huffman* h) {
    int code = 0, first = 0, index = 0;
    for (int len = 1; len <= MAX_BITS; len++) {
        code |= (int)Bits(s, 1);
        if (s->error) return -1;
        const int count = h->count[len];
        if (code - count < first) return h->symbol[index + (code - first)];
        index += count;
        first += count;
        first <<= 1;
        code <<= 1;
    }
    s->error = 1;
    return -1;
}

// Builds the decoding tables from code lengths. Returns 0 for a complete code, negative for an
// over-subscribed one, positive for an incomplete one.
static int Construct(Huffman* h, const uint16_t* length, int n) {
    uint16_t offs[MAX_BITS + 1];
    for (int len = 0; len <= MAX_BITS; len++) h->count[len] = 0;
    for (int sym = 0; sym < n; sym++) h->count[length[sym]]++;
    if (h->count[0] == n) return 0; // no codes at all
    int left = 1;
    for (int len = 1; len <= MAX_BITS; len++) {
        left <<= 1;
        left -= h->count[len];
        if (left < 0) return left;
    }
    offs[1] = 0;
    for (int len = 1; len < MAX_BITS; len++) offs[len + 1] = (uint16_t)(offs[len] + h->count[len]);
    for (int sym = 0; sym < n; sym++) {
        if (length[sym] != 0) h->symbol[offs[length[sym]]++] = (uint16_t)sym;
    }
    return left;
}

// Decodes literals and length/distance pairs until the end-of-block symbol. Returns 1 when the
// output buffer is full.
static int Codes(Inflater* s, const Huffman* lencode, const Huffman* distcode) {
    static const uint16_t lens[29] = { 3,  4,  5,  6,  7,  8,  9,  10, 11,  13,  15,  17,  19,  23, 27,
                                       31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258 };
    static const uint16_t lext[29] = { 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0 };
    static const uint16_t dists[30] = { 1,   2,   3,   4,   5,   7,    9,    13,   17,   25,   33,   49,   65,    97,    129,
                                        193, 257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577 };
    static const uint16_t dext[30] = { 0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13 };
    for (;;) {
        int symbol = Decode(s, lencode);
        if (s->error) return 0;
        if (symbol < 256) {
            if (s->outPos >= s->outLen) return 1;
            s->out[s->outPos++] = (uint8_t)symbol;
        } else if (symbol == 256) {
            return 0;
        } else {
            symbol -= 257;
            if (symbol >= 29) {
                s->error = 1;
                return 0;
            }
            size_t len = lens[symbol] + Bits(s, lext[symbol]);
            symbol = Decode(s, distcode);
            if (s->error || symbol >= 30) {
                s->error = 1;
                return 0;
            }
            const size_t dist = dists[symbol] + Bits(s, dext[symbol]);
            if (s->error || dist > s->outPos) {
                s->error = 1;
                return 0;
            }
            while (len--) {
                if (s->outPos >= s->outLen) return 1;
                s->out[s->outPos] = s->out[s->outPos - dist];
                s->outPos++;
            }
        }
    }
}

static int StoredBlock(Inflater* s) {
    s->bitBuf = 0;
    s->bitCount = 0;
    if (s->inLen - s->inPos < 4) {
        s->error = 1;
        return 0;
    }
    size_t len = Le16(s->in + s->inPos);
    if (len != (Le16(s->in + s->inPos + 2) ^ 0xFFFF) || s->inLen - s->inPos - 4 < len) {
        s->error = 1;
        return 0;
    }
    s->inPos += 4;
    int full = 0;
    if (len > s->outLen - s->outPos) {
        len = s->outLen - s->outPos;
        full = 1;
    }
    memcpy(s->out + s->outPos, s->in + s->inPos, len);
    s->inPos += len;
    s->outPos += len;
    return full;
}

static int FixedBlock(Inflater* s) {
    static Huffman lencode, distcode;
    static int built = 0;
    if (!built) {
        uint16_t lengths[FIXED_LITERAL_CODES];
        int sym = 0;
        for (; sym < 144; sym++) lengths[sym] = 8;
        for (; sym < 256; sym++) lengths[sym] = 9;
        for (; sym < 280; sym++) lengths[sym] = 7;
        for (; sym < FIXED_LITERAL_CODES; sym++) lengths[sym] = 8;
        Construct(&lencode, lengths, FIXED_LITERAL_CODES);
        for (sym = 0; sym < MAX_DISTANCE_CODES; sym++) lengths[sym] = 5;
        Construct(&distcode, lengths, MAX_DISTANCE_CODES);
        built = 1;
    }
    return Codes(s, &lencode, &distcode);
}

static int DynamicBlock(Inflater* s) {
    static const uint8_t order[19] = { 16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15 };
    uint16_t lengths[MAX_LITERAL_CODES + MAX_DISTANCE_CODES];
    Huffman lencode, distcode;
    const int nlen = (int)Bits(s, 5) + 257;
    const int ndist = (int)Bits(s, 5) + 1;
    const int ncode = (int)Bits(s, 4) + 4;
    if (s->error || nlen > MAX_LITERAL_CODES || ndist > MAX_DISTANCE_CODES) {
        s->error = 1;
        return 0;
    }
    int index = 0;
    for (; index < ncode; index++) lengths[order[index]] = (uint16_t)Bits(s, 3);
    for (; index < 19; index++) lengths[order[index]] = 0;
    if (s->error || Construct(&lencode, lengths, 19) != 0) {
        s->error = 1;
        return 0;
    }
    index = 0;
    while (index < nlen + ndist) {
        int symbol = Decode(s, &lencode);
        if (s->error) return 0;
        if (symbol < 16) {
            lengths[index++] = (uint16_t)symbol;
        } else {
            int len = 0, repeat;
            if (symbol == 16) {
                if (index == 0) {
                    s->error = 1;
                    return 0;
                }
                len = lengths[index - 1];
                repeat = 3 + (int)Bits(s, 2);
            } else if (symbol == 17) {
                repeat = 3 + (int)Bits(s, 3);
            } else {
                repeat = 11 + (int)Bits(s, 7);
            }
            if (s->error || index + repeat > nlen + ndist) {
                s->error = 1;
                return 0;
            }
            while (repeat--) lengths[index++] = (uint16_t)len;
        }
    }
    if (lengths[256] == 0) { // no end-of-block code
        s->error = 1;
        return 0;
    }
    int err = Construct(&lencode, lengths, nlen);
    if (err < 0 || (err > 0 && nlen - lencode.count[0] != 1)) s->error = 1;
    err = Construct(&distcode, lengths + nlen, ndist);
    if (err < 0 || (err > 0 && ndist - distcode.count[0] != 1)) s->error = 1;
    return s->error ? 0 : Codes(s, &lencode, &distcode);
}

// Inflates `in` into `out`. Returns the number of bytes written (outLen when the buffer filled
// before the data ended), or (size_t)-1 on bad data.
static size_t Inflate(const uint8_t* in, size_t inLen, uint8_t* out, size_t outLen) {
    Inflater s = { in, inLen, 0, 0, 0, out, outLen, 0, 0 };
    int last, full = 0;
    do {
        last = (int)Bits(&s, 1);
        const int type = (int)Bits(&s, 2);
        if (s.error) break;
        if (type == 0) full = StoredBlock(&s);
        else if (type == 1) full = FixedBlock(&s);
        else if (type == 2) full = DynamicBlock(&s);
        else s.error = 1;
    } while (!last && !full && !s.error);
    return s.error ? (size_t)-1 : s.outPos;
}

// ---- zip ----------------------------------------------------------------------------------

uint32_t Zip_Crc32(const uint8_t* data, size_t len) {
    static uint32_t table[256];
    if (!table[1]) {
        for (uint32_t i = 0; i < 256; i++) {
            uint32_t c = i;
            for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            table[i] = c;
        }
    }
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;
}

static uint8_t* ReadAt(FILE* f, long offset, size_t len) {
    uint8_t* data = malloc(len ? len : 1);
    if (data && (fseek(f, offset, SEEK_SET) != 0 || fread(data, 1, len, f) != len)) {
        free(data);
        data = NULL;
    }
    return data;
}

int Zip_List(const char* path, ZipEntry* out, int max) {
    FILE* f = fopen(path, "rb");
    if (!f) return -1;
    int count = -1;
    uint8_t* tail = NULL;
    uint8_t* central = NULL;
    fseek(f, 0, SEEK_END);
    const long fileSize = ftell(f);
    const size_t tailLen = fileSize < EOCD_SEARCH ? (size_t)fileSize : EOCD_SEARCH;
    if (fileSize < EOCD_SIZE || !(tail = ReadAt(f, fileSize - (long)tailLen, tailLen))) goto done;
    // The end record is found from the back: its comment may follow it.
    size_t at = tailLen - EOCD_SIZE;
    while (memcmp(tail + at, "PK\x05\x06", 4) != 0) {
        if (at-- == 0) goto done;
    }
    const uint32_t entries = Le16(tail + at + 10);
    const uint32_t centralSize = Le32(tail + at + 12);
    const uint32_t centralOffset = Le32(tail + at + 16);
    if (centralOffset == 0xFFFFFFFFu || (uint64_t)centralOffset + centralSize > (uint64_t)fileSize) goto done; // ZIP64
    if (!(central = ReadAt(f, (long)centralOffset, centralSize))) goto done;
    count = 0;
    size_t pos = 0;
    for (uint32_t i = 0; i < entries && pos + CENTRAL_SIZE <= centralSize; i++) {
        const uint8_t* e = central + pos;
        if (memcmp(e, "PK\x01\x02", 4) != 0) break;
        const uint32_t nameLen = Le16(e + 28);
        const size_t next = pos + CENTRAL_SIZE + nameLen + Le16(e + 30) + Le16(e + 32);
        if (next > centralSize) break;
        const uint32_t method = Le16(e + 10);
        const int encrypted = Le16(e + 8) & 1;
        if (count < max && nameLen > 0 && nameLen < ZIP_NAME_LEN && !encrypted &&
            (method == METHOD_STORED || method == METHOD_DEFLATED) && e[CENTRAL_SIZE + nameLen - 1] != '/') {
            ZipEntry* z = &out[count++];
            memcpy(z->name, e + CENTRAL_SIZE, nameLen);
            z->name[nameLen] = '\0';
            z->method = method;
            z->crc = Le32(e + 16);
            z->packedSize = Le32(e + 20);
            z->size = Le32(e + 24);
            z->headerOffset = Le32(e + 42);
        }
        pos = next;
    }
done:
    free(tail);
    free(central);
    fclose(f);
    return count;
}

uint8_t* Zip_Read(const char* path, const ZipEntry* entry, size_t want, size_t* len) {
    FILE* f = fopen(path, "rb");
    if (!f) return NULL;
    uint8_t* result = NULL;
    uint8_t* packed = NULL;
    uint8_t* header = ReadAt(f, (long)entry->headerOffset, LOCAL_SIZE);
    if (!header || memcmp(header, "PK\x03\x04", 4) != 0) goto done;
    const long dataAt = (long)entry->headerOffset + LOCAL_SIZE + (long)Le16(header + 26) + (long)Le16(header + 28);
    const int whole = want == 0 || want >= entry->size;
    const size_t outLen = whole ? entry->size : want;
    uint8_t* out = NULL;
    if (entry->method == METHOD_STORED) {
        out = ReadAt(f, dataAt, outLen);
    } else {
        // For just the start of an entry, the start of its packed data is enough: deflate never
        // needs more input than the output it makes, plus a little.
        size_t packedLen = entry->packedSize;
        if (!whole && packedLen > outLen + 0x10000) packedLen = outLen + 0x10000;
        packed = ReadAt(f, dataAt, packedLen);
        out = packed ? malloc(outLen ? outLen : 1) : NULL;
        if (out && Inflate(packed, packedLen, out, outLen) != outLen) {
            free(out);
            out = NULL;
        }
    }
    if (out && whole && Zip_Crc32(out, outLen) != entry->crc) { // damaged zip, or a decoding mistake
        free(out);
        out = NULL;
    }
    if (out) *len = outLen;
    result = out;
done:
    free(header);
    free(packed);
    fclose(f);
    return result;
}
