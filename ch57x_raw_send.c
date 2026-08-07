#include <libusb-1.0/libusb.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VID 0x1189
#define PID 0x8890
#define IFACE 1
#define ENDPOINT 0x02
#define TIMEOUT_MS 100

static int parse_byte(const char *s, unsigned char *out) {
    char *end = NULL;
    long v = strtol(s, &end, 0);
    if (!s[0] || *end || v < 0 || v > 255) return -1;
    *out = (unsigned char)v;
    return 0;
}

int main(int argc, char **argv) {
    int init_zero = 0;
    int first_byte = 1;

    if (argc > 1 && strcmp(argv[1], "--init-zero") == 0) {
        init_zero = 1;
        first_byte = 2;
    }

    if (argc <= first_byte || argc - first_byte > 64) {
        fprintf(stderr, "usage: %s [--init-zero] <up to 64 report bytes>\n", argv[0]);
        fprintf(stderr, "example: %s 0x03 0xfe 0xb0 0x01 0x01\n", argv[0]);
        return 2;
    }

    unsigned char report[64];
    memset(report, 0, sizeof(report));
    for (int i = first_byte; i < argc; i++) {
        if (parse_byte(argv[i], &report[i - first_byte]) != 0) {
            fprintf(stderr, "invalid byte: %s\n", argv[i]);
            return 2;
        }
    }

    libusb_context *ctx = NULL;
    libusb_device_handle *handle = NULL;
    int rc = libusb_init(&ctx);
    if (rc != 0) return 1;

    handle = libusb_open_device_with_vid_pid(ctx, VID, PID);
    if (!handle) {
        fprintf(stderr, "device %04x:%04x not found\n", VID, PID);
        libusb_exit(ctx);
        return 1;
    }

    libusb_set_auto_detach_kernel_driver(handle, 1);
    rc = libusb_claim_interface(handle, IFACE);
    if (rc != 0) {
        fprintf(stderr, "claim interface failed: %s\n", libusb_error_name(rc));
        libusb_close(handle);
        libusb_exit(ctx);
        return 1;
    }

    int transferred = 0;
    if (init_zero) {
        unsigned char init[64] = {0};
        rc = libusb_interrupt_transfer(handle, ENDPOINT, init, sizeof(init), &transferred, TIMEOUT_MS);
        if (rc != 0) {
            fprintf(stderr, "init write failed: %s\n", libusb_error_name(rc));
            libusb_release_interface(handle, IFACE);
            libusb_close(handle);
            libusb_exit(ctx);
            return 1;
        }
    }

    transferred = 0;
    rc = libusb_interrupt_transfer(handle, ENDPOINT, report, sizeof(report), &transferred, TIMEOUT_MS);
    if (rc != 0) {
        fprintf(stderr, "write failed: %s\n", libusb_error_name(rc));
    } else if (transferred != 64) {
        fprintf(stderr, "short write: %d bytes\n", transferred);
        rc = 1;
    }

    libusb_release_interface(handle, IFACE);
    libusb_close(handle);
    libusb_exit(ctx);
    return rc == 0 ? 0 : 1;
}
