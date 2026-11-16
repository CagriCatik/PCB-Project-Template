// Application uses the existing board_io interface; no GPIO is selected here.
#include <Arduino.h>
#include "app/heartbeat.h"
extern "C" const board_io_t *bsp_esp32_io(void);
extern "C" void bsp_esp32_init(void);
static heartbeat_t heartbeat;
void setup()
{
    bsp_esp32_init();
    // An unassigned indicator returns HEARTBEAT_ERR_IO; no pin is driven.
    (void)heartbeat_init(&heartbeat, bsp_esp32_io(), 1000u, 200u);
}
void loop()
{
    (void)heartbeat_poll(&heartbeat);
    delay(1); // Yield; application watchdog/fail-safe policy still needs design.
}
