/* Exercise the real library's receive/send path; no desktop or credentials. */
#include <rfb/rfbclient.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* This helper is exported by LibVNCClient but absent from its public header. */
extern void rfbClientEncryptBytes(unsigned char *bytes, char *password);
static unsigned char incoming[40];
static unsigned int cursor;
static unsigned char outgoing[34];
static unsigned int written;
rfbBool ReadFromRFBServer(rfbClient *client, char *buf, unsigned int n) {
    (void)client;
    if (cursor + n > sizeof(incoming)) return FALSE;
    memcpy(buf, incoming + cursor, n); cursor += n; return TRUE;
}
rfbBool WriteToRFBServer(rfbClient *client, const char *buf, unsigned int n) {
    (void)client;
    if (written + n > sizeof(outgoing)) return FALSE;
    memcpy(outgoing + written, buf, n); written += n; return TRUE;
}
#define CHECK(condition, message) do { if (!(condition)) { puts("FAIL: " message); return 1; } } while (0)
int main(void) {
    /* Public fixture: verify VNC DES authentication before testing resize. */
    unsigned char challenge[16];
    for (unsigned int i = 0; i < 16; ++i) challenge[i] = i;
    const unsigned char response[16] = {0xb8, 0x66, 0x92, 0x41, 0x25, 0xc8, 0xee, 0xbb, 0x9d, 0xeb, 0xc1, 0xdb, 0x61, 0xc5, 0x38, 0xe2};
    rfbClientEncryptBytes(challenge, "password");
    CHECK(memcmp(challenge, response, 16) == 0, "VNC password authentication backend");
    rfbClient *client = rfbGetClient(8, 3, 4);
    client->width = 1920; client->height = 1080;
    incoming[3] = 1; /* FramebufferUpdate: one rectangle. */
    uint16_t width = htons(1920), height = htons(1080);
    uint32_t encoding = htonl(rfbEncodingExtDesktopSize), flags = htonl(123);
    memcpy(incoming + 8, &width, 2); memcpy(incoming + 10, &height, 2);
    memcpy(incoming + 12, &encoding, 4);
    incoming[16] = 1; /* Single screen, ID zero is valid. */
    memcpy(incoming + 28, &width, 2); memcpy(incoming + 30, &height, 2);
    memcpy(incoming + 32, &flags, 4);
    CHECK(HandleRFBServerMessage(client), "screen advertisement handling");
    CHECK(client->screen.width == width, "valid screen ID zero was ignored");
    const char *zoom = getenv("LEGION_REMMINA_ZOOM");
    unsigned int column = zoom && strcmp(zoom, "125") == 0 ? 2 :
        zoom && strcmp(zoom, "150") == 0 ? 4 : 0;
    const unsigned int cases[][6] = {
        {1600, 900, 1280, 720, 1067, 600},
        {2561, 1601, 2049, 1281, 1707, 1067},
        {1920, 1080, 1536, 864, 1280, 720},
        {1280, 720, 1024, 576, 853, 480},
    };
    for (unsigned int i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        written = 0;
        CHECK(SendExtDesktopSize(client, cases[i][0], cases[i][1]), "resize request failed");
        CHECK(written >= 24, "no resize request emitted");
        rfbSetDesktopSizeMsg request;
        rfbExtDesktopScreen screen;
        memcpy(&request, outgoing, sizeof(request));
        memcpy(&screen, outgoing + sizeof(request), sizeof(screen));
        unsigned int expected_width = cases[i][column];
        unsigned int expected_height = cases[i][column + 1];
        CHECK(request.pad1 == 0 && request.pad2 == 0, "uninitialized request padding");
        CHECK(screen.id == 0 && screen.x == 0 && screen.y == 0, "invalid screen layout");
        CHECK(screen.flags == flags, "screen flags were lost");
        CHECK(request.width == htons(expected_width) && request.height == htons(expected_height), "wrong zoom request size");
        CHECK(screen.width == request.width && screen.height == request.height, "screen size differs from desktop size");
        written = 0;
        CHECK(SendExtDesktopSize(client, cases[i][0], cases[i][1]), "repeated resize failed");
        CHECK(written == 0, "unchanged viewport caused another resize");
    }
    printf("PASS: authentication, screen ID zero, valid layouts, %s%% zoom and repeated resizes\n", column == 2 ? "125" : column == 4 ? "150" : "100");
    rfbClientCleanup(client);
    return 0;
}
