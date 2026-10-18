// Arduino implementation of bsp/board_io.h. LED_BUILTIN is the Uno's on-board
// LED (D13); route your own shield indicator here once it exists in the schematic.
#include <Arduino.h>

#include "bsp/board_io.h"

static uint32_t arduino_millis(void *ctx)
{
    (void)ctx;
    return millis();
}

static bool arduino_set_status(void *ctx, bool on)
{
    (void)ctx;
    digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
    return true;
}

static const board_io_t arduino_io = {arduino_millis, arduino_set_status, nullptr};

extern "C" const board_io_t *bsp_arduino_io(void)
{
    return &arduino_io;
}
