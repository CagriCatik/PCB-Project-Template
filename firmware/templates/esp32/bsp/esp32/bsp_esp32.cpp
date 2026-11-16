#include <Arduino.h>
#include "bsp/board_io.h"
#include "board_pins.h"
static uint32_t esp32_millis(void *ctx)
{
    (void)ctx;
    return millis();
}
static bool esp32_set_status(void *ctx, bool on)
{
    (void)ctx;
#if BSP_STATUS_GPIO >= 0
    digitalWrite(BSP_STATUS_GPIO, (on != bool(BSP_STATUS_ACTIVE_LOW)) ? HIGH : LOW);
    return true;
#else
    (void)on;
    return false; // Intentionally unbound hardware, not a successful write.
#endif
}
static const board_io_t io = {esp32_millis, esp32_set_status, nullptr};
extern "C" const board_io_t *bsp_esp32_io(void) { return &io; }
extern "C" void bsp_esp32_init(void)
{
#if BSP_STATUS_GPIO >= 0
    digitalWrite(BSP_STATUS_GPIO, BSP_STATUS_ACTIVE_LOW ? HIGH : LOW);
    pinMode(BSP_STATUS_GPIO, OUTPUT);
#endif
}
