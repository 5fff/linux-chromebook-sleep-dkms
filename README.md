# ChromeOS EC Suspend Failsafe Patch (DKMS)

A native DKMS kernel module patch for non-ChromeOS Linux (like Fedora) running on modern Chromebooks (e.g., Acer Spin 714).

> [!WARNING]
> **Disclaimer:** This project is an independent, community-driven workaround and is **not** affiliated with, authorized by, sponsored by, or in any way officially connected to Google LLC, Google Embedded Controller developers, or any of their affiliates. 
> 
> Kernel-level modifications carry inherent risk. By using this software, you agree that you are doing so at your own risk. The author(s) of this project are **not responsible** for any data loss, hardware damage, system instability, or if this software somehow fries your computer. Use with caution!

## The Problem
When a standard Linux kernel attempts to suspend, it sends a `HOST_SLEEP_EVENT` to the ChromeOS Embedded Controller (EC) with an uninitialized `0ms` timeout (since Google's `powerd` daemon is not running). 

Because modern Intel laptops rely on `s2idle` (S0ix) which doesn't reliably trigger the hardware sleep pins the EC expects, the EC interprets the 0ms timeout as a fatal error and triggers a hardware watchdog reset after 20 seconds, hard-crashing the laptop.

## The Solution
This DKMS module patches `cros_ec_proto.c` to intercept the `HOST_SLEEP_EVENT` command. It modifies the payload to inject an infinite timeout (`0xFFFF`), completely disabling the EC's hardware watchdog and allowing the laptop to sleep safely. 

This safely bypasses the crash while allowing the kernel's own software suspend watchdog to maintain protection against driver hangs.

## Installation

The easiest and most reliable way to install the sleep failsafe is via the pre-built RPM package, which automatically handles DKMS compilation and applies the necessary Wi-Fi/KDE power tweaks for true S0i3 deep sleep.

### 1. Install the RPM
Download the latest `.rpm` release and install it via `dnf`:

```bash
sudo dnf install ./cros-ec-sleep-fix-dkms-1.0-1.fc42.noarch.rpm
```

### 2. Enroll MOK for Secure Boot (Only applicable if Secure Boot is Enabled)
If your Chromebook has UEFI Secure Boot enabled, the kernel will refuse to load the locally-compiled module until you authorize the signing key.

To trust this key, run this command in your terminal **after** the RPM finishes installing:
```bash
sudo mokutil --import /var/lib/dkms/mok.pub
```
1. **Create a Password:** When prompted, create a simple temporary password.
2. **Reboot:** Restart your laptop.
3. **Enroll MOK:** On the blue pre-boot `MOKManager` screen, select **Enroll MOK** -> **Continue** -> **Yes**, enter the temporary password you created, and select **Reboot**.


### 3. Reboot
A reboot is required for the patched kernel module and power tweaks to take effect.

```bash
sudo reboot
```

## Uninstallation

To completely remove the DKMS module, unregister the kprobes, and delete the power tweaks, simply uninstall the package via `dnf`:

```bash
sudo dnf remove cros-ec-sleep-fix-dkms
sudo reboot
```
## Manual DKMS Installation
If you prefer not to use the RPM package or are on a non-Fedora distribution (like Ubuntu/Arch), you can build and install the module manually using DKMS.

1. Copy the source files to `/usr/src`:
   ```bash
   sudo mkdir -p /usr/src/cros-ec-sleep-fix-1.0
   sudo cp cros_ec_sleep_kprobe.c Makefile dkms.conf /usr/src/cros-ec-sleep-fix-1.0/
   ```

2. Register, build, and install with DKMS:
   ```bash
   sudo dkms add -m cros-ec-sleep-fix -v 1.0
   sudo dkms build -m cros-ec-sleep-fix -v 1.0
   sudo dkms install -m cros-ec-sleep-fix -v 1.0
   ```

3. Ensure it loads on boot:
   ```bash
   echo "cros_ec_sleep_kprobe" | sudo tee /etc/modules-load.d/cros-ec-sleep-fix.conf
   echo "softdep cros_ec_sleep_kprobe pre: cros_ec_proto" | sudo tee /etc/modprobe.d/cros_ec_sleep_kprobe.conf
   ```

4. Reboot your system.

*(Note: Manual installation will not automatically apply the Wi-Fi power-saving tweaks required for true S0i3 deep sleep. See the "Achieving True S0i3" section below to apply them yourself).*

## Achieving True S0i3 (Optional)
While this patch makes `s2idle` completely safe, you may notice that the power button LED stays solid blue instead of pulsing orange during sleep. This happens because the Intel CPU refuses to enter its deepest hardware sleep state (S0i3) if certain devices fail to power down.

The most common culprit on Fedora is the Intel Wi-Fi driver (`iwlwifi`). By default, Fedora disables Wi-Fi power saving, which leaves the Wi-Fi card in state `D0` and completely blocks S0i3.

To enable Wi-Fi power saving and allow the CPU to reach S0i3 (pulsing light + maximum battery life):
```bash
echo 'options iwlwifi power_save=1' | sudo tee /etc/modprobe.d/iwlwifi.conf
```
After a reboot, the `iwlwifi` module will allow the CNVi block to suspend, enabling true S0ix hardware sleep.

## Fixing Intel Audio Crashes on Wake
On some 13th-Gen Intel Chromebooks, the Sound Open Firmware (SOF) driver often fails to restore IPC communication (`error -22`) after waking up from deep hardware sleep, leaving the laptop without sound.

This is an upstream Linux bug affecting specific Chromebook audio topologies (like the Maxim/Nuvoton combo). Since this sleep failsafe module successfully enables true deep sleep for the first time, you may begin encountering this audio wake bug.

To fix audio issues on Chromebooks running Linux, it is highly recommended to use the dedicated [WeirdTreeThing/chromebook-linux-audio](https://github.com/WeirdTreeThing/chromebook-linux-audio) project, which provides comprehensive, community-maintained audio fixes and firmware topologies for Chromebooks.

## How the RPM Packaging Works (Plain Words)

To keep both development and distribution as simple as possible, this project does not distribute pre-compiled binary modules. Instead:

1. **The RPM contains only source code:** When you build the RPM, it packages the raw C source code (`cros_ec_sleep_kprobe.c`), the `Makefile`, and the `dkms.conf` config. No compiled binaries are included.
2. **On-Device Local Compilation:** When you install the RPM on the Chromebook, the source files are extracted and compiled **locally on the Chromebook itself**. This ensures that the module is built perfectly for the Chromebook's specific CPU architecture and running kernel version, preventing compatibility issues.
3. **DKMS Integration & Kernel Upgrade Persistence:** Once compiled, the module is registered with **DKMS (Dynamic Kernel Module Support)**. This guarantees that the module automatically survives system and kernel updates:
    * **Source Preservation:** The RPM permanently places the raw source code (`cros_ec_sleep_kprobe.c`, `Makefile`, and `dkms.conf`) inside `/usr/src/cros-ec-sleep-fix-dkms-1.0/`.
    * **Kernel Upgrade Hook:** Whenever Fedora installs a new kernel (via `dnf upgrade`), a package manager hook automatically alerts DKMS of the new kernel version.
    * **Automatic Background Build:** Before the machine even reboots into the new kernel, DKMS compiles a new version of the module against the newly-installed kernel headers. If Secure Boot is enabled, DKMS also automatically signs the new module using the local Machine Owner Key (MOK) you enrolled during first install.
    * **Seamless Boot:** When the Chromebook boots into the updated kernel, the module is loaded automatically and is immediately active, ensuring the sleep fix never breaks on upgrade.

---

## Building the RPM (For Developers)
If you are modifying the source code or packaging it for a new Fedora release, you can rebuild the RPM directly from this repository:

1. Package the modified source files into a tarball:
   ```bash
   cd rpmbuild/SOURCES/
   mkdir -p cros-ec-sleep-fix-dkms-1.0
   cp ../../cros_ec_sleep_kprobe.c ../../Makefile ../../dkms.conf cros-ec-sleep-fix-dkms-1.0/
   cp -r ../../modprobe.d ../../environment.d ../../modules-load.d cros-ec-sleep-fix-dkms-1.0/
   tar -czvf cros-ec-sleep-fix-dkms-1.0.tar.gz cros-ec-sleep-fix-dkms-1.0/
   rm -rf cros-ec-sleep-fix-dkms-1.0/
   cd ../..
   ```

2. Build the `.rpm` package using `rpmbuild`:
   ```bash
   rpmbuild -ba --define "_topdir $(pwd)/rpmbuild" rpmbuild/SPECS/cros-ec-sleep-fix-dkms.spec
   ```

The newly built package will be available in `rpmbuild/RPMS/noarch/`.

For more background on why eBPF was insufficient and why this DKMS patch was necessary, read `PROJECT_CONTEXT.md` and `DKMS_DESIGN.md`.
