#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

struct sample {
    uint64_t job, release_ns, start_ns, finish_ns;
    uint64_t wakeup_delay_ns, execution_ns, response_ns;
    int64_t lateness_ns;
    int miss, cpu;
};

static uint64_t to_ns(const struct timespec *ts) {
    return (uint64_t)ts->tv_sec * 1000000000ULL + (uint64_t)ts->tv_nsec;
}

static void add_ns(struct timespec *ts, uint64_t ns) {
    uint64_t value = (uint64_t)ts->tv_nsec + ns;
    ts->tv_sec += (time_t)(value / 1000000000ULL);
    ts->tv_nsec = (long)(value % 1000000000ULL);
}

static uint64_t now_raw_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC_RAW, &ts) != 0) { perror("clock_gettime"); exit(2); }
    return to_ns(&ts);
}

static void payload(uint64_t iters) {
    volatile double x = 1.0;
    for (uint64_t i = 0; i < iters; ++i) x = x * 1.0000001 + 0.0000001;
    (void)x;
}

static uint64_t calibrate(uint64_t period_ns, double load) {
    const uint64_t target = (uint64_t)((double)period_ns * load);
    uint64_t iters = 50000;
    for (int k = 0; k < 20; ++k) {
        uint64_t begin = now_raw_ns();
        payload(iters);
        uint64_t elapsed = now_raw_ns() - begin;
        if (elapsed == 0) elapsed = 1;
        if (elapsed >= target * 99 / 100 && elapsed <= target * 101 / 100) return iters;
        double scale = (double)target / (double)elapsed;
        if (scale < 0.5) scale = 0.5;
        if (scale > 2.0) scale = 2.0;
        iters = (uint64_t)((double)iters * scale);
        if (iters < 1000) iters = 1000;
    }
    return iters;
}

static void usage(const char *prog) {
    fprintf(stderr,
        "usage: %s [--period ns] [--deadline ns] [--duration s] "
        "[--iters n | --calibrate-only] [--cpu-load x] [--out path] "
        "[--shock-fifo path] [--shock-threshold ns] [--mlock]\n", prog);
}

int main(int argc, char **argv) {
    uint64_t period_ns = 5000000, deadline_ns = 3000000, duration_s = 500;
    uint64_t iters = 0, shock_threshold_ns = 10000000;
    double cpu_load = 0.12;
    const char *out_path = "out.csv", *shock_fifo = NULL;
    bool calibrate_only = false, do_mlock = false;

    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--period") && i + 1 < argc) period_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--deadline") && i + 1 < argc) deadline_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--duration") && i + 1 < argc) duration_s = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--iters") && i + 1 < argc) iters = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--cpu-load") && i + 1 < argc) cpu_load = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out_path = argv[++i];
        else if (!strcmp(argv[i], "--shock-fifo") && i + 1 < argc) shock_fifo = argv[++i];
        else if (!strcmp(argv[i], "--shock-threshold") && i + 1 < argc) shock_threshold_ns = strtoull(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--calibrate-only")) calibrate_only = true;
        else if (!strcmp(argv[i], "--mlock")) do_mlock = true;
        else { usage(argv[0]); return 2; }
    }

    if (period_ns == 0 || deadline_ns == 0 || duration_s == 0 || cpu_load <= 0.0) {
        fprintf(stderr, "invalid numeric argument\n"); return 2;
    }
    if (calibrate_only) {
        printf("%" PRIu64 "\n", calibrate(period_ns, cpu_load));
        return 0;
    }
    if (iters == 0) {
        fprintf(stderr, "--iters is mandatory during measurements; run calibrate.sh first\n");
        return 2;
    }

    size_t capacity = (size_t)(duration_s * 1000000000ULL / period_ns) + 4;
    struct sample *samples = calloc(capacity, sizeof(*samples));
    if (!samples) { perror("calloc"); return 1; }
    if (do_mlock && mlockall(MCL_CURRENT | MCL_FUTURE) != 0) { perror("mlockall"); return 1; }

    int shock_fd = -1;
    if (shock_fifo) shock_fd = open(shock_fifo, O_WRONLY | O_NONBLOCK | O_CLOEXEC);

    struct sched_param sp = {0};
    sched_getparam(0, &sp);
    fprintf(stderr, "pid=%ld tid=%ld policy=%d priority=%d cpu=%d iters=%" PRIu64 "\n",
            (long)getpid(), (long)syscall(SYS_gettid), sched_getscheduler(0),
            sp.sched_priority, sched_getcpu(), iters);

    struct timespec next;
    if (clock_gettime(CLOCK_MONOTONIC, &next) != 0) { perror("clock_gettime"); return 1; }
    uint64_t end_ns = to_ns(&next) + duration_s * 1000000000ULL;
    size_t count = 0;
    bool shock_sent = false;

    while (count < capacity) {
        int rc;
        do { rc = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &next, NULL); } while (rc == EINTR);
        if (rc != 0) { fprintf(stderr, "clock_nanosleep: %s\n", strerror(rc)); return 1; }

        struct timespec begin, finish;
        clock_gettime(CLOCK_MONOTONIC, &begin);
        payload(iters);
        clock_gettime(CLOCK_MONOTONIC, &finish);

        struct sample *s = &samples[count];
        s->job = count;
        s->release_ns = to_ns(&next);
        s->start_ns = to_ns(&begin);
        s->finish_ns = to_ns(&finish);
        s->wakeup_delay_ns = s->start_ns - s->release_ns;
        s->execution_ns = s->finish_ns - s->start_ns;
        s->response_ns = s->finish_ns - s->release_ns;
        s->lateness_ns = (int64_t)s->response_ns - (int64_t)deadline_ns;
        s->miss = s->lateness_ns > 0;
        s->cpu = sched_getcpu();
        ++count;

        if (!shock_sent && shock_fd >= 0 && s->response_ns >= shock_threshold_ns) {
            char msg[192];
            int n = snprintf(msg, sizeof(msg),
                "TDPS_SHOCK job=%" PRIu64 " release_ns=%" PRIu64 " start_ns=%" PRIu64
                " finish_ns=%" PRIu64 " response_ns=%" PRIu64 " cpu=%d\n",
                s->job, s->release_ns, s->start_ns, s->finish_ns, s->response_ns, s->cpu);
            if (n > 0 && write(shock_fd, msg, (size_t)n) > 0) shock_sent = true;
        }

        add_ns(&next, period_ns);
        if (s->finish_ns >= end_ns) break;
    }

    if (shock_fd >= 0) close(shock_fd);
    FILE *out = fopen(out_path, "w");
    if (!out) { perror("fopen"); return 1; }
    fprintf(out, "job,release_ns,start_ns,finish_ns,wakeup_delay_ns,execution_ns,response_ns,lateness_ns,miss,cpu\n");
    for (size_t i = 0; i < count; ++i) {
        const struct sample *s = &samples[i];
        fprintf(out, "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
                     ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRId64 ",%d,%d\n",
                s->job, s->release_ns, s->start_ns, s->finish_ns,
                s->wakeup_delay_ns, s->execution_ns, s->response_ns,
                s->lateness_ns, s->miss, s->cpu);
    }
    if (fclose(out) != 0) { perror("fclose"); return 1; }
    free(samples);
    return 0;
}
