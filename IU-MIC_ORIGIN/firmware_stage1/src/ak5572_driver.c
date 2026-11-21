#include "ak5572_driver.h"

static uint8_t mode_to_cks_nibble(iu_aoip_mode_t mode) {
    /* AK5572EN CKS[3:0] with 24.576 MHz MCLK (Master/Auto-clock mode):
     *   48 kHz  -> 512fs (Normal Speed)
     *   192 kHz -> 128fs (Quad Speed)
     *   384 kHz -> 64fs  (Octal Speed)
     * NOTE: Verify exact CKS[3:0] table code against AK5572EN Rev datasheet Table 11 on target bench! */
    switch (mode) {
        case AOIP_MODE_A_AES67_48K: return 0x02U; /* Normal Speed 512fs */
        case AOIP_MODE_B_RTP_192K:  return 0x06U; /* Quad Speed 128fs */
        case AOIP_MODE_B_RTP_384K:  return 0x0EU; /* Octal Speed 64fs */
        default:                    return 0x0EU;
    }
}

int ak5572_init(ak5572_dev_t *dev, const ak5572_cfg_t *cfg) {
    if (!dev || !cfg || !dev->write_reg) return -1;

    /* 1. Assert internal reset (RSTN = 0) before modifying clock/mode registers */
    uint8_t mono_bits = cfg->mono_2to1_summation ? (0x01U << 1) : 0x00U;
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_PWR_MGMT2, mono_bits, dev->user_ctx) != 0) return -2;

    /* 2. Power up both CH1 & CH2 (required for 2-to-1 Mono Summation) */
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_PWR_MGMT1, 0xFFU, dev->user_ctx) != 0) return -3;

    /* 3. Control 1: CKS[3:0] | DIF[1:0]=10 (24-bit I2S) | HPFE */
    uint8_t cks = mode_to_cks_nibble(cfg->mode) & 0x0FU;
    uint8_t ctrl1 = (uint8_t)((cks << 3) | (0x02U << 1) | (cfg->digital_hpf_enable ? 1U : 0U));
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_CTRL1, ctrl1, dev->user_ctx) != 0) return -4;

    /* 4. Control 2: Normal I2S (TDM = 00) */
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_CTRL2, 0x00U, dev->user_ctx) != 0) return -5;

    /* 5. Control 3 / DSD1: PCM mode (DP=0) + SD/SLOW digital filter select */
    uint8_t ctrl3 = (uint8_t)((cfg->filter_sd_slow & 0x03U) << 5);
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_CTRL3_DSD1, ctrl3, dev->user_ctx) != 0) return -6;

    /* 6. Release reset (RSTN = 1) keeping MONO[2:1] active */
    if (dev->write_reg(dev->i2c_addr7, AK5572_REG_PWR_MGMT2, (uint8_t)(mono_bits | 0x01U), dev->user_ctx) != 0) return -7;

    return 0;
}
