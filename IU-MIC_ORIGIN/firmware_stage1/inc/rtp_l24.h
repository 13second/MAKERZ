#ifndef RTP_L24_H
#define RTP_L24_H

#include <stddef.h>
#include <stdint.h>
#include "iu_mic_config.h"

typedef struct {
    uint32_t ssrc;
    uint16_t seq;
    uint32_t timestamp;
    uint8_t  payload_type;
    iu_aoip_mode_t mode;
} rtp_l24_ctx_t;

void rtp_l24_init(rtp_l24_ctx_t *ctx, uint32_t ssrc, iu_aoip_mode_t mode);

/* Combines AK5572EN CH1 + CH2 (signed 24-bit in int32_t) in 2-to-1 Mono Summation */
int32_t ak5572_combine_2to1_mono(int32_t ch1_s24, int32_t ch2_s24);

/* Packs `num_samples` signed 24-bit PCM samples into RFC 3550 + RFC 3190 big-endian RTP packet.
 * Returns total packet length in bytes, or 0 on error. */
size_t rtp_l24_pack(rtp_l24_ctx_t *ctx, const int32_t *pcm24, size_t num_samples,
                    uint8_t *out_buf, size_t out_cap);

/* Unpacks RFC 3550 + RFC 3190 L24 RTP packet back into signed 24-bit samples (loopback/receiver).
 * Returns number of decoded samples, or 0 on invalid packet. */
size_t rtp_l24_unpack(const uint8_t *pkt, size_t pkt_len,
                      uint16_t *out_seq, uint32_t *out_ts,
                      int32_t *out_pcm24, size_t max_samples);

/* Simple boxcar/CIC-stage 8x decimator (384 kHz -> 48 kHz for Mode A AES67 bring-up) */
int32_t decimate_8x_sample(const int32_t in_8[8]);

#endif /* RTP_L24_H */
