#ifndef IU_MIC_CONFIG_H
#define IU_MIC_CONFIG_H

#include <stdint.h>

/* =========================================================================
 * IU-MIC_ORIGIN — Stadio 1 Bring-Up Configuration (STM32H743VIT6 LQFP-100)
 * D1: 20 Hz - 80 kHz | D2: 384 kHz / 24-bit | D3: AES67 48k + RTP L24 192/384k
 * D4: Percorso Singolo (G=1.25x) + AK5572EN 2-to-1 Mono Summation (124 dB DR)
 * ========================================================================= */

typedef enum {
    AOIP_MODE_A_AES67_48K = 0,   /* 48 kHz / 24-bit L24, 1 ms packet (48 samples) */
    AOIP_MODE_B_RTP_192K  = 1,   /* 192 kHz / 24-bit L24, 250 us packet (48 samples) */
    AOIP_MODE_B_RTP_384K  = 2    /* 384 kHz / 24-bit L24, 125 us packet (48 samples) */
} iu_aoip_mode_t;

/* Master Audio Clock: 24.576 MHz low-jitter TCXO */
#define IU_MCLK_HZ                  24576000UL
#define IU_SAMPLES_PER_PKT          48U          /* 48 mono 24-bit samples = 144 B payload */
#define IU_RTP_HEADER_BYTES         12U
#define IU_RTP_L24_PAYLOAD_BYTES    (IU_SAMPLES_PER_PKT * 3U)
#define IU_RTP_PKT_BYTES            (IU_RTP_HEADER_BYTES + IU_RTP_L24_PAYLOAD_BYTES)
#define IU_RTP_PAYLOAD_TYPE_L24     96U          /* Dynamic PT per AES67 / RFC 3190 */

/* STM32H743VIT6 (LQFP-100) verified RMII Pinout (T1: NO Port G on LQFP-100!) */
#define IU_ETH_REF_CLK_PIN          "PA1 (AF11)"
#define IU_ETH_MDIO_PIN             "PA2 (AF11)"
#define IU_ETH_MDC_PIN              "PC1 (AF11)"
#define IU_ETH_CRS_DV_PIN           "PA7 (AF11)"
#define IU_ETH_RXD0_PIN             "PC4 (AF11)"
#define IU_ETH_RXD1_PIN             "PC5 (AF11)"
#define IU_ETH_TX_EN_PIN            "PB11 (AF11)"
#define IU_ETH_TXD0_PIN             "PB12 (AF11)"
#define IU_ETH_TXD1_PIN             "PB13 (AF11)"

/* ADC Full-Scale Differential Input (T1 verified: AK5572EN @ AVDD=5.0V) */
#define IU_ADC_VFS_RMS              1.979899f    /* 5.6 Vpp / (2*sqrt(2)) */
#define IU_AFE_GAIN_LIN             1.249f       /* +1.93 dB (D4) */

#endif /* IU_MIC_CONFIG_H */
