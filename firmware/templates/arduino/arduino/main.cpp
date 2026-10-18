// Arduino entry point: wires the platform-independent heartbeat to the Arduino BSP.
#include <Arduino.h>

#include "app/heartbeat.h"

extern "C" const board_io_t *bsp_arduino_io(void);

static heartbeat_t heartbeat;

void setup()
{
    pinMode(LED_BUILTIN, OUTPUT);
    heartbeat_init(&heartbeat, bsp_arduino_io(), 1000u, 200u);
}

void loop()
{
    heartbeat_poll(&heartbeat);
}
