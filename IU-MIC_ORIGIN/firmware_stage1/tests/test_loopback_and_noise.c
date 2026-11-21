#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "iu_mic_config.h"
#include "rtp_l24.h"
#include "ptp_sync.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

static double gauss_rand(uint64_t *state) {
    /* Deterministic Box-Muller PRNG for reproducible noise-floor verification */
    double u1, u2;
    do {
        *state = (*state * 6364136223846793005ULL + 1442695040888963407ULL);
        u1 = ((double)(*state >> 11) / (double)(1ULL << 53));
    } while (u1 <= 1e-12);
    *state = (*state * 6364136223846793005ULL + 1442695040888963407ULL);
    u2 = ((double)(*state >> 11) / (double)(1ULL << 53));
    return sqrt(-2.0 * log(u1)) * cos(2.0 * M_PI * u2);
}

static void test_rtp_l24_loopback(void) {
    rtp_l24_ctx_t tx;
    rtp_l24_init(&tx, 0x49554D31UL, AOIP_MODE_B_RTP_384K);

    int32_t tx_pcm[IU_SAMPLES_PER_PKT];
    int32_t rx_pcm[IU_SAMPLES_PER_PKT];
    uint8_t wire_buf[IU_RTP_PKT_BYTES];

    int32_t max_lsb_err = 0;
    const double fs = 384000.0;
    const double f_sig = 40000.0; /* 40 kHz ultrasonic test tone @ -1 dBFS */
    const double amp = 8388607.0 * pow(10.0, -1.0 / 20.0);

    for (uint32_t pkt = 0; pkt < 100; ++pkt) {
        for (size_t i = 0; i < IU_SAMPLES_PER_PKT; ++i) {
            double t = (double)(pkt * IU_SAMPLES_PER_PKT + i) / fs;
            tx_pcm[i] = (int32_t)llround(amp * sin(2.0 * M_PI * f_sig * t));
        }
        size_t nbytes = rtp_l24_pack(&tx, tx_pcm, IU_SAMPLES_PER_PKT, wire_buf, sizeof(wire_buf));
        assert(nbytes == IU_RTP_PKT_BYTES);

        uint16_t seq = 0;
        uint32_t ts = 0;
        size_t n_dec = rtp_l24_unpack(wire_buf, nbytes, &seq, &ts, rx_pcm, IU_SAMPLES_PER_PKT);
        assert(n_dec == IU_SAMPLES_PER_PKT);
        assert(seq == (uint16_t)pkt);
        assert(ts == pkt * IU_SAMPLES_PER_PKT);

        for (size_t i = 0; i < IU_SAMPLES_PER_PKT; ++i) {
            int32_t err = abs(tx_pcm[i] - rx_pcm[i]);
            if (err > max_lsb_err) max_lsb_err = err;
        }
    }
    printf("[PASS] Test 1 — RTP L24 Loopback (384 kHz, 40 kHz tone, 100 pkt): max_err = %d LSB\n", max_lsb_err);
    assert(max_lsb_err == 0);
}

static void test_noise_floor_and_2to1_mono(void) {
    /* Verify +3.0 dB uncorrelated ADC noise reduction of ak5572_combine_2to1_mono() through RTP L24 */
    const double vfs_pk = IU_ADC_VFS_RMS * sqrt(2.0); /* 2.80 Vpk diff */
    const double sigma_adc_1ch_v = 3.53e-6;           /* AK5572 1-ch 80kHz noise from T2 */
    const double sigma_adc_lsb = (sigma_adc_1ch_v / vfs_pk) * 8388607.0;

    uint64_t rng = 0x123456789ABCDEF0ULL;
    const size_t N = 48000;
    double sum_sq_1ch = 0.0;
    double sum_sq_mono = 0.0;

    rtp_l24_ctx_t tx;
    rtp_l24_init(&tx, 0x49554D31UL, AOIP_MODE_B_RTP_384K);
    uint8_t wire_buf[IU_RTP_PKT_BYTES];
    int32_t mono_blk[IU_SAMPLES_PER_PKT];
    int32_t rx_blk[IU_SAMPLES_PER_PKT];

    for (size_t b = 0; b < N / IU_SAMPLES_PER_PKT; ++b) {
        for (size_t i = 0; i < IU_SAMPLES_PER_PKT; ++i) {
            int32_t c1 = (int32_t)llround(sigma_adc_lsb * gauss_rand(&rng));
            int32_t c2 = (int32_t)llround(sigma_adc_lsb * gauss_rand(&rng));
            sum_sq_1ch += (double)c1 * (double)c1;
            mono_blk[i] = ak5572_combine_2to1_mono(c1, c2);
        }
        size_t nb = rtp_l24_pack(&tx, mono_blk, IU_SAMPLES_PER_PKT, wire_buf, sizeof(wire_buf));
        size_t nd = rtp_l24_unpack(wire_buf, nb, NULL, NULL, rx_blk, IU_SAMPLES_PER_PKT);
        assert(nd == IU_SAMPLES_PER_PKT);
        for (size_t i = 0; i < IU_SAMPLES_PER_PKT; ++i) {
            sum_sq_mono += (double)rx_blk[i] * (double)rx_blk[i];
        }
    }

    double rms_1ch_lsb = sqrt(sum_sq_1ch / (double)N);
    double rms_mono_lsb = sqrt(sum_sq_mono / (double)N);
    double rms_1ch_uv = (rms_1ch_lsb / 8388607.0) * vfs_pk * 1e6;
    double rms_mono_uv = (rms_mono_lsb / 8388607.0) * vfs_pk * 1e6;
    double gain_snr_db = 20.0 * log10(rms_1ch_lsb / rms_mono_lsb);
    double floor_dbfs = 20.0 * log10(rms_mono_lsb / (8388607.0 / sqrt(2.0)));

    printf("[PASS] Test 2 — Misura Rumore 2-to-1 Mono + RTP L24:\n");
    printf("       1-ch ADC RMS: %.2f uVrms | 2-to-1 Mono RMS: %.2f uVrms (%.2f dBFS) | Miglioramento SNR: +%.2f dB\n",
           rms_1ch_uv, rms_mono_uv, floor_dbfs, gain_snr_db);
    assert(gain_snr_db > 2.8 && gain_snr_db < 3.2);
}

static void test_ptp_servo_convergence(void) {
    ptp_servo_t s;
    ptp_servo_init(&s);
    int64_t slave_err_ns = 25000; /* 25 us initial clock offset */
    for (int step = 0; step < 30; ++step) {
        int64_t t1 = 1000000LL * step;
        int64_t delay = 400; /* 400 ns link delay */
        int64_t t2 = t1 + delay + slave_err_ns;
        int64_t t3 = t2 + 10000;
        int64_t t4 = t3 + delay - slave_err_ns;
        int32_t corr = ptp_servo_update(&s, t1, t2, t3, t4);
        slave_err_ns += corr;
    }
    printf("[PASS] Test 3 — PTPv2 Servo Convergence (25 us -> %lld ns, lock_count=%u)\n",
           (long long)s.offset_ns, s.lock_count);
    assert(llabs(s.offset_ns) < 1000 && s.lock_count >= 5);
}

int main(void) {
    test_rtp_l24_loopback();
    test_noise_floor_and_2to1_mono();
    test_ptp_servo_convergence();
    printf("GATE T9 (Host Bring-Up Loopback + Noise + PTPv2): PASS\n");
    return 0;
}
