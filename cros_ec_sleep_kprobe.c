#include <linux/module.h>
#include <linux/kprobes.h>
#include <linux/platform_data/cros_ec_commands.h>
#include <linux/platform_data/cros_ec_proto.h>
#include <linux/ptrace.h>

static struct kprobe kp = {
    .symbol_name = "cros_ec_cmd_xfer",
};

static int handler_pre(struct kprobe *p, struct pt_regs *regs)
{
    /* Use the generic architecture-independent arg access (index 1 for 2nd arg) */
    struct cros_ec_command *msg = (struct cros_ec_command *)regs_get_kernel_argument(regs, 1);

    if (msg && msg->command == EC_CMD_HOST_SLEEP_EVENT && msg->version == 1) {
        struct ec_params_host_sleep_event_v1 *req = (struct ec_params_host_sleep_event_v1 *)msg->data;

        if (req->sleep_event == HOST_SLEEP_EVENT_S0IX_SUSPEND ||
            req->sleep_event == HOST_SLEEP_EVENT_S3_SUSPEND ||
            req->sleep_event == HOST_SLEEP_EVENT_S3_WAKEABLE_SUSPEND) {

            req->suspend_params.sleep_timeout_ms = 0xFFFF; // Infinite
            pr_info("CHROMEOS SLEEP FIX: Suspend detected. Setting HOST_SLEEP_EVENT timeout to infinite (0xFFFF) via kprobe.\n");
        }
    }
    return 0;
}

static int __init cros_ec_sleep_kprobe_init(void)
{
    kp.pre_handler = handler_pre;
    if (register_kprobe(&kp) < 0) {
        pr_err("cros_ec_sleep_kprobe: failed to register kprobe\n");
        return -1;
    }
    pr_info("cros_ec_sleep_kprobe: registered\n");
    return 0;
}

static void __exit cros_ec_sleep_kprobe_exit(void)
{
    unregister_kprobe(&kp);
    pr_info("cros_ec_sleep_kprobe: unregistered\n");
}

module_init(cros_ec_sleep_kprobe_init);
module_exit(cros_ec_sleep_kprobe_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Kprobe-based ChromeOS sleep fix");
MODULE_AUTHOR("Ray X");
