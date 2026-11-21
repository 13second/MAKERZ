#ifndef AK5572_DRIVER_H
#define AK5572_DRIVER_H

#include <stdbool.h>
#include <stdint.h>
#include "iu_mic_config.h"

/* AKM AK5572EN Official I2C Register Addresses (Datasheet Register Map 00H-04H) */
#define AK5572_I2C_ADDR_BASE     0x10U  /* 7-bit: 0b00100[CAD1][CAD0] (0x10..0x13) */
#define AK5572_REG_PWR_MGMT1     0x00U  /* [1:0] PW2, PW1 (default upper bits 1) */
#define AK5572_REG_PWR_MGMT2     0x01U  /* [2:1] MONO2, MONO1 | [0] RSTN */
#define AK5572_REG_CTRL1         0x02U  /* [6:3] CKS3..0 | [2:1] DIF1..0 | [0] HPFE */
#define AK5572_REG_CTRL2         0x03U  /* [6:5] TDM1..0 */
#define AK5572_REG_CTRL3_DSD1    0x04U  /* [7] DP | [6] SD | [5] SLOW */

typedef int (*ak5572_i2c_write_fn)(uint8_t dev_addr7, uint8_t reg, uint8_t val, void *user);
typedef int (*ak5572_i2c_read_fn)(uint8_t dev_addr7, uint8_t reg, uint8_t *val, void *user);

typedef struct {
    uint8_t              i2c_addr7;
    ak5572_i2c_write_fn  write_reg;
    ak5572_i2c_read_fn   read_reg;
    void                *user_ctx;
} ak5572_dev_t;

typedef struct {
    iu_aoip_mode_t mode;
    bool           mono_2to1_summation;  /* D4: true -> 124 dB DR */
    bool           digital_hpf_enable;   /* DC-blocking internal HPF */
    uint8_t        filter_sd_slow;       /* 0=Sharp, 1=Slow, 2=SD Sharp, 3=SD Slow */
} ak5572_cfg_t;

int ak5572_init(ak5572_dev_t *dev, const ak5572_cfg_t *cfg);

#endif /* AK5572_DRIVER_H */
