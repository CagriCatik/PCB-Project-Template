#include "app/heartbeat.h"

#include <stddef.h>

static uint32_t active_period(const heartbeat_t *hb)
{
    return hb->fault ? hb->fault_period_ms : hb->period_ms;
}

heartbeat_status_t heartbeat_init(heartbeat_t *hb, const board_io_t *io, uint32_t period_ms,
                                  uint32_t fault_period_ms)
{
    if (hb == NULL || io == NULL || io->millis == NULL || io->set_status == NULL || period_ms < 2u ||
        fault_period_ms < 2u) {
        return HEARTBEAT_ERR_ARG;
    }
    hb->io = io;
    hb->period_ms = period_ms;
    hb->fault_period_ms = fault_period_ms;
    hb->last_toggle_ms = io->millis(io->ctx);
    hb->output_on = false;
    hb->fault = false;
    hb->io_errors = 0u;
    if (!io->set_status(io->ctx, false)) {
        hb->io_errors++;
        return HEARTBEAT_ERR_IO;
    }
    return HEARTBEAT_OK;
}

heartbeat_status_t heartbeat_poll(heartbeat_t *hb)
{
    if (hb == NULL || hb->io == NULL) {
        return HEARTBEAT_ERR_ARG;
    }
    const uint32_t now = hb->io->millis(hb->io->ctx);
    /* Unsigned subtraction stays correct across the 32-bit millisecond wrap. */
    if ((uint32_t)(now - hb->last_toggle_ms) < active_period(hb) / 2u) {
        return HEARTBEAT_OK;
    }
    const bool next = !hb->output_on;
    hb->last_toggle_ms = now;
    if (!hb->io->set_status(hb->io->ctx, next)) {
        /* Keep the logical state unchanged so the next poll retries the write. */
        hb->io_errors++;
        return HEARTBEAT_ERR_IO;
    }
    hb->output_on = next;
    return HEARTBEAT_OK;
}

void heartbeat_set_fault(heartbeat_t *hb, bool fault)
{
    if (hb != NULL) {
        hb->fault = fault;
    }
}
