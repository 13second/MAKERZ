#include "rtp_l24.h"

static inline int32_t clamp_s24(int32_t x) {
    if (x > 8388607) return 8388607;
    if (x < -8388608) return -8388608;
    return x;
}

void rtp_l24_init(rtp_l24_ctx_t *ctx, uint32_t ssrc, iu_aoip_mode_t mode) {
    ctx->ssrc = ssrc;
    ctx->seq = 0;
    ctx->timestamp = 0;
    ctx->payload_type = IU_RTP_PAYLOAD_TYPE_L24;
    ctx->mode = mode;
}

int32_t ak5572_combine_2to1_mono(int32_t ch1_s24, int32_t ch2_s24) {
    /* Unbiased round-to-nearest-even average of dual-channel AK5572EN (+3.01 dB SNR) */
    int64_t sum = (int64_t)ch1_s24 + (int64_t)ch2_s24;
    int64_t q = sum / 2;
    int64_t r = sum % 2;
    if (r != 0 && (q & 1)) {
        q += (sum > 0) ? 1 : -1;
    }
    return clamp_s24((int32_t)q);
}

size_t rtp_l24_pack(rtp_l24_ctx_t *ctx, const int32_t *pcm24, size_t num_samples,
                    uint8_t *out_buf, size_t out_cap) {
    const size_t total_len = IU_RTP_HEADER_BYTES + num_samples * 3U;
    if (!ctx || !pcm24 || !out_buf || out_cap < total_len) return 0;

    /* RFC 3550 Fixed 12-Byte RTP Header (Big-Endian) */
    out_buf[0]  = 0x80U; /* V=2, P=0, X=0, CC=0 */
    out_buf[1]  = (uint8_t)(ctx->payload_type & 0x7FU);
    out_buf[2]  = (uint8_t)(ctx->seq >> 8);
    out_buf[3]  = (uint8_t)(ctx->seq & 0xFFU);
    out_buf[4]  = (uint8_t)(ctx->timestamp >> 24);
    out_buf[5]  = (uint8_t)(ctx->timestamp >> 16);
    out_buf[6]  = (uint8_t)(ctx->timestamp >> 8);
    out_buf[7]  = (uint8_t)(ctx->timestamp & 0xFFU);
    out_buf[8]  = (uint8_t)(ctx->ssrc >> 24);
    out_buf[9]  = (uint8_t)(ctx->ssrc >> 16);
    out_buf[10] = (uint8_t)(ctx->ssrc >> 8);
    out_buf[11] = (uint8_t)(ctx->ssrc & 0xFFU);

    /* RFC 3190 L24 Payload: 24-bit signed big-endian PCM */
    uint8_t *p = out_buf + IU_RTP_HEADER_BYTES;
    for (size_t i = 0; i < num_samples; ++i) {
        int32_t s = clamp_s24(pcm24[i]);
        p[0] = (uint8_t)((s >> 16) & 0xFF);
        p[1] = (uint8_t)((s >> 8) & 0xFF);
        p[2] = (uint8_t)(s & 0xFF);
        p += 3;
    }

    ctx->seq++;
    ctx->timestamp += (uint32_t)num_samples;
    return total_len;
}

size_t rtp_l24_unpack(const uint8_t *pkt, size_t pkt_len,
                      uint16_t *out_seq, uint32_t *out_ts,
                      int32_t *out_pcm24, size_t max_samples) {
    if (!pkt || pkt_len < IU_RTP_HEADER_BYTES || ((pkt_len - IU_RTP_HEADER_BYTES) % 3U) != 0) {
        return 0;
    }
    if ((pkt[0] & 0xC0U) != 0x80U) return 0; /* Must be RTP v2 */

    const size_t n = (pkt_len - IU_RTP_HEADER_BYTES) / 3U;
    if (n > max_samples) return 0;

    if (out_seq) *out_seq = (uint16_t)(((uint16_t)pkt[2] << 8) | pkt[3]);
    if (out_ts)  *out_ts  = ((uint32_t)pkt[4] << 24) | ((uint32_t)pkt[5] << 16) |
                            ((uint32_t)pkt[6] << 8)  | (uint32_t)pkt[7];

    const uint8_t *p = pkt + IU_RTP_HEADER_BYTES;
    for (size_t i = 0; i < n; ++i) {
        int32_t raw = ((int32_t)p[0] << 16) | ((int32_t)p[1] << 8) | (int32_t)p[2];
        /* Sign-extend 24-bit -> 32-bit */
        if (raw & 0x00800000) raw |= (int32_t)0xFF000000;
        out_pcm24[i] = raw;
        p += 3;
    }
    return n;
}

int32_t decimate_8x_sample(const int32_t in_8[8]) {
    int64_t acc = 0;
    for (int i = 0; i < 8; ++i) acc += in_8[i];
    return clamp_s24((int32_t)(acc / 8));
}
