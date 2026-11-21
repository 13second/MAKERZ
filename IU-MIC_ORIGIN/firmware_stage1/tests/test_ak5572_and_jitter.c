#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include "ak5572_driver.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* Mock I2C register bank to verify exact AK5572EN initialization sequence & readback */
typedef struct {
    uint8_t regs[8];
    uint8_t addr_seen;
    int     rstn_held_low_during_cfg;
    int     write_count;
} mock_ak5572_bus_t;

static int mock_i2c_write(uint8_t addr7, uint8_t reg, uint8_t val, void *user) {
    mock_ak5572_bus_t *b = (mock_ak5572_bus_t *)user;
    b->addr_seen = addr7;
    if (reg == AK5572_REG_CTRL1) {
        /* Verify RSTN was 0 when writing Control 1 (clock/format register) */
        b->rstn_held_low_during_cfg = ((b->regs[AK5572_REG_PWR_MGMT2] & 0x01U) == 0U);
    }
    if (reg < 8) b->regs[reg] = val;
    b->write_count++;
    return 0;
}

static void test_ak5572_register_map(void) {
    mock_ak5572_bus_t bus = {0};
    ak5572_dev_t dev = {
        .i2c_addr7 = AK5572_I2C_ADDR_BASE, /* CAD1=0, CAD0=0 -> 0x10 */
        .write_reg = mock_i2c_write,
        .read_reg  = NULL,
        .user_ctx  = &bus,
    };
    ak5572_cfg_t cfg = {
        .mode = AOIP_MODE_B_RTP_384K,
        .mono_2to1_summation = true,
        .digital_hpf_enable = true,
        .filter_sd_slow = 0, /* Sharp Roll-off */
    };

    int rc = ak5572_init(&dev, &cfg);
    assert(rc == 0);
    assert(bus.addr_seen == 0x10U);
    assert(bus.rstn_held_low_during_cfg == 1);
    assert(bus.regs[AK5572_REG_PWR_MGMT1] == 0xFFU);          /* CH1+CH2 ON */
    assert(bus.regs[AK5572_REG_PWR_MGMT2] == 0x03U);          /* MONO 2-to-1 + RSTN=1 */
    assert((bus.regs[AK5572_REG_CTRL1] & 0x07U) == 0x05U);    /* 24-bit I2S + HPFE=1 */
    assert(bus.regs[AK5572_REG_CTRL3_DSD1] == 0x00U);         /* PCM Sharp Roll-off */

    printf("[PASS] Test 4 — AK5572EN I2C Register Map & Reset Sequence (addr=0x%02X, 0x00=0x%02X, 0x01=0x%02X, 0x02=0x%02X, 0x04=0x%02X)\n",
           bus.addr_seen, bus.regs[0], bus.regs[1], bus.regs[2], bus.regs[4]);
}

static double snr_jitter_db(double f_sig_hz, double sigma_t_sec) {
    return -20.0 * log10(2.0 * M_PI * f_sig_hz * sigma_t_sec);
}

static void test_mclk_jitter_budget_80khz(void) {
    const double f_ultra = 80000.0;
    const double snr_pll_50ps  = snr_jitter_db(f_ultra, 50e-12);  /* STM32H7 internal PLL */
    const double snr_tcxo_05ps = snr_jitter_db(f_ultra, 0.5e-12); /* Dedicated 24.576 MHz osc */

    printf("[PASS] Test 5 — Budget Jitter Clock MCLK (24.576 MHz) @ f_sig = 80 kHz:\n");
    printf("       STM32 PLL interna (50 ps_rms):  SNR_jitter = %.1f dB  [INSUFFICIENTE vs 105.6 dB capsula!]\n", snr_pll_50ps);
    printf("       Oscillatore dedicato (0.5 ps):  SNR_jitter = %.1f dB  [OK: +26.4 dB sopra capsula, +8.0 dB sopra AK5572 124 dB!]\n", snr_tcxo_05ps);
    assert(snr_pll_50ps < 95.0);
    assert(snr_tcxo_05ps > 124.0);
}

int main(void) {
    test_ak5572_register_map();
    test_mclk_jitter_budget_80khz();
    printf("GATE T9-EXT (AK5572 I2C Driver + MCLK Jitter Budget): PASS\n");
    return 0;
}
