#include "ptp_sync.h"

void ptp_servo_init(ptp_servo_t *s) {
    s->offset_ns = 0;
    s->integral_err = 0.0;
    s->addend_ppb = 0;
    s->lock_count = 0;
}

int32_t ptp_servo_update(ptp_servo_t *s, int64_t t1_master_ns, int64_t t2_slave_ns,
                         int64_t t3_slave_ns, int64_t t4_master_ns) {
    /* Standard IEEE 1588 delay-request/response offset formula:
     * offset = ((t2 - t1) - (t4 - t3)) / 2 */
    s->offset_ns = ((t2_slave_ns - t1_master_ns) - (t4_master_ns - t3_slave_ns)) / 2;

    /* PI servo tuning for AES67 (< 1 us lock target) */
    const double kp = 0.35;
    const double ki = 0.05;
    s->integral_err += (double)s->offset_ns;
    if (s->integral_err > 5e6)  s->integral_err = 5e6;
    if (s->integral_err < -5e6) s->integral_err = -5e6;

    double corr = -(kp * (double)s->offset_ns + ki * s->integral_err);
    if (corr > 100000.0)  corr = 100000.0;
    if (corr < -100000.0) corr = -100000.0;
    s->addend_ppb = (int32_t)corr;

    if (s->offset_ns > -1000 && s->offset_ns < 1000) {
        s->lock_count++;
    } else {
        s->lock_count = 0;
    }
    return s->addend_ppb;
}
