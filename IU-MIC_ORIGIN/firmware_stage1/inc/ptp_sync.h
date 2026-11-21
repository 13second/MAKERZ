#ifndef PTP_SYNC_H
#define PTP_SYNC_H

#include <stdint.h>

/* IEEE 1588 PTPv2 Hardware Timestamping Servo (STM32H743 ETH MAC) */
typedef struct {
    int64_t  offset_ns;
    double   integral_err;
    int32_t  addend_ppb;
    uint32_t lock_count;
} ptp_servo_t;

void    ptp_servo_init(ptp_servo_t *s);
int32_t ptp_servo_update(ptp_servo_t *s, int64_t t1_master_ns, int64_t t2_slave_ns,
                         int64_t t3_slave_ns, int64_t t4_master_ns);

#endif /* PTP_SYNC_H */
