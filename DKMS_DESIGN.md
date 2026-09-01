# DKMS Kernel Module Design: ChromeOS EC Suspend Failsafe
 
## Background
ChromeOS devices running standard Linux kernels (like Fedora) lack the `powerd` userspace daemon, which natively negotiates sleep timeouts with the Google Embedded Controller (EC). When a standard Linux kernel suspends, it sends a `HOST_SLEEP_EVENT` (Command `0x00A9`) to the EC with an uninitialized `suspend_timeout_ms` of `0ms`.
 
The EC interprets a `0ms` timeout as a hard deadline. If the host CPU takes longer than `0ms` to assert its hardware sleep pin—which is guaranteed to happen on an active desktop environment—the EC assumes the CPU has crashed during suspend and fires a hardware watchdog reset, instantly rebooting the laptop.
 
## Why eBPF Failed
We attempted to mitigate this by intercepting the `0x00A9` command using eBPF (`kprobe` on `cros_ec_cmd_xfer`). However:
1. **Memory Modification Blocked:** eBPF cannot overwrite the `0ms` payload because `cros_ec_command` is in kernel memory, blocking `bpf_probe_write_user`.
2. **Function Drop Blocked:** We cannot override the function return to silently drop the packet because `cros_ec_cmd_xfer` lacks the `ALLOW_ERROR_INJECTION` kernel macro.
3. **Delay Strategy Deadlocks:** We successfully built a massive `bpf_loop` to stall the packet transmission, attempting to give the CPU a "head start" to sleep. However, holding the `cros_ec_cmd_xfer` thread hostage blocks the hardware bus mutex. While this worked perfectly on some boot cycles (giving us the illusion of success), on other boot cycles the active desktop suspend sequence required subsequent EC commands (like `0x2b` Motion Sense) to finish tearing down. When the bus is held hostage, the kernel `suspend_test.c` watchdog detects a deadlock, aborts the entire sleep process, and forces an immediate wake-up.
 
## The DKMS Solution (Kprobe Architecture)
Since we cannot manipulate the kernel state safely from the outside, but copying the entire `cros_ec_proto.c` is brittle and susceptible to breakage during kernel upgrades, we use a much cleaner approach: **kprobes**.

By injecting a tiny, native C Kernel Module that registers a `kprobe` (Kernel Probe) on the `cros_ec_cmd_xfer` function, we intercept the command exactly as it is processed by the kernel. Because the module is built natively against the running kernel headers using **DKMS**, we have unrestricted, ring-0 access to memory.

Instead of overriding the entire module, we simply patch the `msg->data` inline:

```c
static int handler_pre(struct kprobe *p, struct pt_regs *regs)
{
    /* Use the architecture-independent arg access (index 1 for 2nd arg) */
    struct cros_ec_command *msg = (struct cros_ec_command *)regs_get_kernel_argument(regs, 1);

    if (msg && msg->command == EC_CMD_HOST_SLEEP_EVENT && msg->version == 1) {
        struct ec_params_host_sleep_event_v1 *req = (struct ec_params_host_sleep_event_v1 *)msg->data;
        
        if (req->sleep_event == HOST_SLEEP_EVENT_S0IX_SUSPEND ||
            req->sleep_event == HOST_SLEEP_EVENT_S3_SUSPEND || 
            req->sleep_event == HOST_SLEEP_EVENT_S3_WAKEABLE_SUSPEND) {
            
            req->suspend_params.sleep_timeout_ms = 0xFFFF; // Infinite
        }
    }
    return 0;
}
```

### Why this is superior
- **Future-Proof**: We do not hardcode *any* internal functions of the `cros_ec_proto` stack. Even if Linux radically refactors the rest of the ChromeOS driver, our module will continue compiling and hooking perfectly as long as the main transfer function is used.
- **Zero Delay**: The execution finishes instantly, preventing bus mutex deadlocks.
- **Native Memory Access**: Being natively compiled, there are no `-EFAULT` restrictions on modifying the pointer's memory.
 
### Implementation Steps
1. Create a DKMS module directory (e.g., `/usr/src/cros-ec-sleep-fix-dkms-1.0`).
2. Include the `cros_ec_sleep_kprobe.c` source code.
3. Create a `Makefile` and `dkms.conf` that builds the `cros_ec_sleep_kprobe.ko` module and installs it into the `extra` directory.
4. Run `dkms install`, and ensure `modules-load.d` configuration automatically loads it on boot.

### Secure Boot Considerations
Because DKMS compiles out-of-tree kernel modules locally on the user's machine, the newly built `.ko` driver file will **not** be signed by Fedora's official Secure Boot keys.

If Secure Boot is enabled, the Linux kernel will strictly refuse to load the newly patched `cros_ec_sleep_kprobe.ko` module (resulting in a "Required key not available" error).

To securely deploy this:
1. **DKMS Auto-Signing:** Modern Fedora DKMS automatically generates a Machine Owner Key (MOK) pair located at `/var/lib/dkms/mok.key` and `/var/lib/dkms/mok.pub`. DKMS automatically signs the built module with this key during RPM installation.
2. **User Enrollment:** The user must manually enroll the public key into their UEFI firmware. This is done by running `sudo mokutil --import /var/lib/dkms/mok.pub`, rebooting the computer, and interacting with the `MOKManager` pre-boot blue screen to enroll the key. Once enrolled, the kernel will trust all modules built by the local DKMS instance.