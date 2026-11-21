/*
 * IU-MIC_ORIGIN — Stadio 1 STM32H743VIT6 Bring-Up Entry Point
 * Catena: SAI1 DMA Double-Buffer (AK5572EN 384 kHz / 24-bit 2ch)
 *      -> ak5572_combine_2to1_mono() (D4: +3 dB SNR -> 124 dB DR)
 *      -> rtp_l24_pack() (Mode A: AES67 48k/24b | Mode B: RTP L24 192/384k)
 *      -> ETH RMII (LAN8742A) + IEEE 1588 PTPv2 HW Timestamping
 *
 * NOTE: Richiede STM32CubeH7 HAL + LwIP nel progetto STM32CubeIDE / CMake target.
 *       I registri I2C esatti dell'AK5572EN vanno confermati sulla Register Map del datasheet AKM prima del flash.
 */
#include "iu_mic_config.h"
#include "rtp_l24.h"
#include "ptp_sync.h"

static rtp_l24_ctx_t g_rtp;
static ptp_servo_t   g_ptp;
static uint8_t       g_udp_tx_buf[IU_RTP_PKT_BYTES];

/* Chiamata dalla ISR DMA Half-Transfer / Transfer-Complete di SAI1 (48 frame stereo = 96 int32) */
void iu_mic_sai1_dma_callback(const int32_t *rx_interleaved_48frames,
                              void (*udp_send_fn)(const uint8_t *buf, size_t len)) {
    int32_t mono_buf[IU_SAMPLES_PER_PKT];
    for (size_t i = 0; i < IU_SAMPLES_PER_PKT; ++i) {
        int32_t ch1 = rx_interleaved_48frames[2U * i] >> 8;     /* 32-bit slot -> signed 24-bit */
        int32_t ch2 = rx_interleaved_48frames[2U * i + 1U] >> 8;
        mono_buf[i] = ak5572_combine_2to1_mono(ch1, ch2);
    }

    size_t pkt_len = rtp_l24_pack(&g_rtp, mono_buf, IU_SAMPLES_PER_PKT,
                                  g_udp_tx_buf, sizeof(g_udp_tx_buf));
    if (pkt_len > 0 && udp_send_fn) {
        udp_send_fn(g_udp_tx_buf, pkt_len);
    }
}

void iu_mic_stage1_init(iu_aoip_mode_t mode) {
    ptp_servo_init(&g_ptp);
    rtp_l24_init(&g_rtp, 0x49554D31UL /* "IUM1" */, mode);
    /* Sequenza bring-up hardware su target STM32H743:
     * 1. Init clock tree (480 MHz SYSCLK, PLL2/3 o MCLK esterno 24.576 MHz su SAI1)
     * 2. Init I2C1 -> reset & config AK5572EN (I2S 24-bit, Quad/Oct Speed 384 kHz)
     * 3. Init ETH RMII (PA1/PA2/PA7/PC1/PC4/PC5/PB11/PB12/PB13) + LAN8742A + PTPv2 HW TS
     * 4. Avvio SAI1 RX DMA circolare double-buffer -> iu_mic_sai1_dma_callback()
     */
}
