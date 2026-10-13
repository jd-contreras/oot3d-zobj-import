// Drawing helpers (citro2d): flat panels, text and touch buttons on both screens.
#pragma once

#include <3ds.h>
#include <citro2d.h>
#include <stdbool.h>

#define TOP_W 400
#define BOTTOM_W 320
#define SCREEN_H 240

// Palette
#define CLR_BG C2D_Color32(0x16, 0x1F, 0x1A, 0xFF)
#define CLR_PANEL C2D_Color32(0x21, 0x2E, 0x27, 0xFF)
#define CLR_HEADER C2D_Color32(0x1F, 0x5C, 0x38, 0xFF)
#define CLR_SEL C2D_Color32(0x2F, 0x7D, 0x4A, 0xFF)
#define CLR_TEXT C2D_Color32(0xEE, 0xEE, 0xEE, 0xFF)
#define CLR_DIM C2D_Color32(0x9A, 0xB2, 0xA3, 0xFF)
#define CLR_ACCENT C2D_Color32(0xF2, 0xC1, 0x4E, 0xFF)
#define CLR_GOOD C2D_Color32(0x7E, 0xE0, 0x8E, 0xFF)
#define CLR_WARN C2D_Color32(0xFF, 0x9E, 0x5E, 0xFF)
#define CLR_ERR C2D_Color32(0xFF, 0x6B, 0x6B, 0xFF)
#define CLR_BTN C2D_Color32(0x2C, 0x40, 0x35, 0xFF)

typedef struct {
    float x, y, w, h;
} ui_box;

void ui_init(void);
void ui_exit(void);

// Frame structure: ui_begin(); ui_top(); ...draw...; ui_bottom(); ...draw...; ui_end();
void ui_begin(void);
void ui_top(void);
void ui_bottom(void);
void ui_end(void);

void ui_rect(float x, float y, float w, float h, u32 color);
void ui_text(float x, float y, float scale, u32 color, const char* fmt, ...) __attribute__((format(printf, 5, 6)));
void ui_text_right(float right_x, float y, float scale, u32 color, const char* fmt, ...)
    __attribute__((format(printf, 5, 6)));
void ui_text_center(float center_x, float y, float scale, u32 color, const char* fmt, ...)
    __attribute__((format(printf, 5, 6)));
void ui_text_wrap(float x, float y, float scale, u32 color, float width, const char* text);
// Draws text shrunk as needed to fit `width`.
void ui_text_fit(float x, float y, float scale, u32 color, float width, const char* text);

bool ui_hit(const ui_box* b, const touchPosition* t);

// Draws one "please wait" frame before a slow operation.
void ui_busy(const char* title, const char* msg);
// Draws one frame of a progress bar: `what` is being done, `fraction` (0-1) of all the work.
void ui_progress(const char* title, const char* what, float fraction);
