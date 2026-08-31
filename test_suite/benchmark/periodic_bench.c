#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>

static inline uint64_t timespec_to_ns(const struct timespec *ts) {
    return (uint64_t)ts->tv_sec * 1000000000ULL + ts->tv_nsec;
}

static inline void add_ns(struct timespec *ts, uint64_t ns) {
    ts->tv_nsec += ns;
    while (ts->tv_nsec >= 1000000000L) {
        ts->tv_nsec -= 1000000000L;
        ts->tv_sec++;
    }
}

static inline uint64_t nsec_now(void){
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
  return (uint64_t)ts.tv_sec*1000000000ull + (uint64_t)ts.tv_nsec;
}

/* Deterministic compute payload */
static void compute_payload(uint64_t iters) {
  volatile double x = 1.0;
  for (uint64_t i = 0; i < iters; i++) {
    x = x * 1.0000001 + 0.0000001;
  }
  (void)x;
}

static uint64_t calibrate_iters(uint64_t period_ns, double util_target) {
  uint64_t target_ns = (uint64_t)(period_ns * util_target);

  uint64_t iters = 50000;
  for (int k = 0; k < 12; k++) {
    uint64_t t0 = nsec_now();
    compute_payload(iters);
    uint64_t dt = nsec_now() - t0;

    if (dt == 0) dt = 1;
    // scale iters proportionally to approach target
    double scale = (double)target_ns / (double)dt;
    if (scale < 0.5) scale = 0.5;
    if (scale > 2.0) scale = 2.0;

    uint64_t new_iters = (uint64_t)(iters * scale);
    if (new_iters < 1000) new_iters = 1000;

    // convergence criterion (~5%)
    if (dt > (target_ns*95)/100 && dt < (target_ns*105)/100) return iters;

    iters = new_iters;
  }
  return iters;
}

int main(int argc, char *argv[]) {
    uint64_t period_ns = 5000000;   // default 5 ms
    uint64_t deadline_ns = 5000000; // default = period
    uint64_t duration_s = 60;       // default 60 s
    uint64_t compute_iters;
    double cpu_load = 0.12;         // default 12%
    const char *out_path = "out.csv";

    /* Simple argument parsing */
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--period") && i + 1 < argc)
            period_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--deadline") && i + 1 < argc)
            deadline_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--duration") && i + 1 < argc)
            duration_s = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--iters") && i + 1 < argc)
            compute_iters = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--out") && i + 1 < argc)
            out_path = argv[++i];
        else if (!strcmp(argv[i], "--cpu_load") && i + 1 < argc)
            cpu_load = strtod(argv[++i], NULL);
    }

    FILE *f = fopen(out_path, "w");
    if (!f) {
        perror("fopen");
        return 1;
    }

    fprintf(f, "job,release_ns,finish_ns,response_ns,lateness_ns,miss\n");

    compute_iters = calibrate_iters(period_ns, cpu_load);


    struct timespec next_release;
    clock_gettime(CLOCK_MONOTONIC, &next_release);

    uint64_t start_ns = timespec_to_ns(&next_release);
    uint64_t end_ns = start_ns + duration_s * 1000000000ULL;

    uint64_t job = 0;

    while (1) {
        int ret;
        do {
            ret = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next_release, NULL);
        } while (ret == EINTR);

        if (ret != 0) {
            fprintf(stderr, "clock_nanosleep error: %s (%d)\n", strerror(ret), ret);
            break;
        }

        struct timespec t_start, t_finish;
        clock_gettime(CLOCK_MONOTONIC, &t_start);

        compute_payload(compute_iters);

        clock_gettime(CLOCK_MONOTONIC, &t_finish);

        uint64_t release_ns = timespec_to_ns(&next_release);
        uint64_t finish_ns  = timespec_to_ns(&t_finish);
        uint64_t response_ns = finish_ns - release_ns;

        int64_t lateness = (int64_t)response_ns - (int64_t)deadline_ns;
        int miss = (lateness > 0);

        fprintf(f, "%lu,%lu,%lu,%lu,%ld,%d\n",
                job, release_ns, finish_ns,
                response_ns, lateness, miss);

        job++;

        add_ns(&next_release, period_ns);

        if (finish_ns >= end_ns)
            break;
    }

    fclose(f);
    return 0;
}
