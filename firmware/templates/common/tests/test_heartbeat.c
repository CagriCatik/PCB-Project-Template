/* Host unit tests: module behaviour plus board_io (hardware interface) edge cases. */
#include <stdio.h>
#include <stdlib.h>

#include "app/heartbeat.h"

typedef struct {
    uint32_t now;
    bool led;
    int writes;
    int fail_writes; /* number of upcoming set_status calls that fail */
} fake_board_t;

static uint32_t fake_millis(void *ctx) { return ((fake_board_t *)ctx)->now; }

static bool fake_set(void *ctx, bool on)
{
    fake_board_t *b = (fake_board_t *)ctx;
    b->writes++;
    if (b->fail_writes > 0) {
        b->fail_writes--;
        return false;
    }
    b->led = on;
    return true;
}

static int failures;
#define CHECK(cond)                                                                 \
    do {                                                                            \
        if (!(cond)) {                                                              \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                                             \
        }                                                                           \
    } while (0)

static void setup(heartbeat_t *hb, fake_board_t *b, board_io_t *io, uint32_t start)
{
    *b = (fake_board_t){.now = start};
    *io = (board_io_t){.millis = fake_millis, .set_status = fake_set, .ctx = b};
    CHECK(heartbeat_init(hb, io, 1000u, 200u) == HEARTBEAT_OK);
}

static void test_rejects_invalid_arguments(void)
{
    heartbeat_t hb;
    fake_board_t b = {0};
    board_io_t io = {.millis = fake_millis, .set_status = fake_set, .ctx = &b};
    board_io_t no_clock = {.millis = NULL, .set_status = fake_set, .ctx = &b};
    CHECK(heartbeat_init(NULL, &io, 1000u, 200u) == HEARTBEAT_ERR_ARG);
    CHECK(heartbeat_init(&hb, NULL, 1000u, 200u) == HEARTBEAT_ERR_ARG);
    CHECK(heartbeat_init(&hb, &no_clock, 1000u, 200u) == HEARTBEAT_ERR_ARG);
    CHECK(heartbeat_init(&hb, &io, 1u, 200u) == HEARTBEAT_ERR_ARG);
    CHECK(heartbeat_poll(NULL) == HEARTBEAT_ERR_ARG);
}

static void test_toggles_every_half_period(void)
{
    heartbeat_t hb;
    fake_board_t b;
    board_io_t io;
    setup(&hb, &b, &io, 0u);
    CHECK(b.led == false);
    b.now = 499u;
    heartbeat_poll(&hb);
    CHECK(b.led == false);
    b.now = 500u;
    heartbeat_poll(&hb);
    CHECK(b.led == true);
    b.now = 1000u;
    heartbeat_poll(&hb);
    CHECK(b.led == false);
}

static void test_millis_wraparound(void)
{
    heartbeat_t hb;
    fake_board_t b;
    board_io_t io;
    setup(&hb, &b, &io, UINT32_MAX - 100u);
    b.now = 398u; /* 499 ms later, across the wrap */
    heartbeat_poll(&hb);
    CHECK(b.led == false);
    b.now = 399u; /* exactly 500 ms */
    heartbeat_poll(&hb);
    CHECK(b.led == true);
}

static void test_missed_polls_toggle_once(void)
{
    heartbeat_t hb;
    fake_board_t b;
    board_io_t io;
    setup(&hb, &b, &io, 0u);
    int before = b.writes;
    b.now = 10000u; /* many periods without polling, e.g. a blocked main loop */
    heartbeat_poll(&hb);
    CHECK(b.writes == before + 1);
    CHECK(b.led == true);
}

static void test_fault_uses_fast_period(void)
{
    heartbeat_t hb;
    fake_board_t b;
    board_io_t io;
    setup(&hb, &b, &io, 0u);
    heartbeat_set_fault(&hb, true);
    b.now = 100u;
    heartbeat_poll(&hb);
    CHECK(b.led == true);
    heartbeat_set_fault(&hb, false);
    b.now = 200u;
    heartbeat_poll(&hb);
    CHECK(b.led == true); /* back to the 1000 ms period */
}

static void test_io_failure_is_reported_and_retried(void)
{
    heartbeat_t hb;
    fake_board_t b;
    board_io_t io;
    setup(&hb, &b, &io, 0u);
    b.fail_writes = 1;
    b.now = 500u;
    CHECK(heartbeat_poll(&hb) == HEARTBEAT_ERR_IO);
    CHECK(hb.io_errors == 1u);
    CHECK(hb.output_on == false);
    b.now = 1000u;
    CHECK(heartbeat_poll(&hb) == HEARTBEAT_OK);
    CHECK(b.led == true);
}

static void test_init_reports_io_failure(void)
{
    heartbeat_t hb;
    fake_board_t b = {.fail_writes = 1};
    board_io_t io = {.millis = fake_millis, .set_status = fake_set, .ctx = &b};
    CHECK(heartbeat_init(&hb, &io, 1000u, 200u) == HEARTBEAT_ERR_IO);
}

int main(void)
{
    test_rejects_invalid_arguments();
    test_toggles_every_half_period();
    test_millis_wraparound();
    test_missed_polls_toggle_once();
    test_fault_uses_fast_period();
    test_io_failure_is_reported_and_retried();
    test_init_reports_io_failure();
    if (failures) {
        fprintf(stderr, "%d check(s) failed\n", failures);
        return EXIT_FAILURE;
    }
    puts("heartbeat: all tests passed");
    return EXIT_SUCCESS;
}
