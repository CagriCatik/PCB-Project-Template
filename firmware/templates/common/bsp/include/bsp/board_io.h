/*
 * Board I/O interface between platform-independent application code and a BSP.
 *
 * The application only sees this function table. Each target (STM32 HAL,
 * Arduino core, host test fake) provides its own implementation, so no
 * target headers ever reach firmware/app.
 */
#ifndef BSP_BOARD_IO_H
#define BSP_BOARD_IO_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct board_io {
    /* Monotonic millisecond counter; may wrap at UINT32_MAX. */
    uint32_t (*millis)(void *ctx);
    /* Drive the status indicator. Returns false if the hardware write failed. */
    bool (*set_status)(void *ctx, bool on);
    void *ctx;
} board_io_t;

#ifdef __cplusplus
}
#endif

#endif /* BSP_BOARD_IO_H */
