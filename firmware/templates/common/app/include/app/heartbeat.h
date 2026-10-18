/*
 * Heartbeat / fault indicator: a platform-independent example module.
 *
 * Toggles the status output every half period; a fault switches to a faster
 * period. Wrap-around safe and tolerant of missed polls (one toggle per poll).
 */
#ifndef APP_HEARTBEAT_H
#define APP_HEARTBEAT_H

#include <stdbool.h>
#include <stdint.h>

#include "bsp/board_io.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    HEARTBEAT_OK = 0,
    HEARTBEAT_ERR_ARG,     /* null pointer, missing callback or period < 2 ms */
    HEARTBEAT_ERR_IO       /* board_io set_status reported a failure */
} heartbeat_status_t;

typedef struct {
    const board_io_t *io;
    uint32_t period_ms;
    uint32_t fault_period_ms;
    uint32_t last_toggle_ms;
    bool output_on;
    bool fault;
    uint32_t io_errors;
} heartbeat_t;

heartbeat_status_t heartbeat_init(heartbeat_t *hb, const board_io_t *io, uint32_t period_ms,
                                  uint32_t fault_period_ms);
heartbeat_status_t heartbeat_poll(heartbeat_t *hb);
void heartbeat_set_fault(heartbeat_t *hb, bool fault);

#ifdef __cplusplus
}
#endif

#endif /* APP_HEARTBEAT_H */
