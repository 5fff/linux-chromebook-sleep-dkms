Name:           cros-ec-sleep-fix-dkms
Version:        1.0
Release:        1%{?dist}
Summary:        DKMS kernel module patch for ChromeOS EC suspend failures

License:        GPLv2
URL:            https://github.com/5fff/cros-ec-sleep-fix
Source0:        %{name}-%{version}.tar.gz

Requires:       dkms >= 2.0.0
Requires:       make
Requires:       gcc
Requires:       kernel-devel

BuildArch:      noarch

%description
A native DKMS kernel module patch for non-ChromeOS Linux (like Fedora) running on modern Chromebooks (e.g., Acer Spin 714).
It safely intercepts the HOST_SLEEP_EVENT to the Google Embedded Controller, injecting an infinite timeout to prevent the 0ms hardware watchdog from crashing the laptop during s2idle suspend.

%prep
%setup -q -n %{name}-%{version}

%build

%install
mkdir -p %{buildroot}/usr/src/%{name}-%{version}
cp -r Makefile cros_ec_sleep_kprobe.c dkms.conf %{buildroot}/usr/src/%{name}-%{version}/

# Install modprobe config to enable iwlwifi power saving for true S0i3
mkdir -p %{buildroot}/etc/modprobe.d
install -m 644 modprobe.d/iwlwifi-s0ix.conf %{buildroot}/etc/modprobe.d/cros-ec-iwlwifi-s0ix.conf

# Install environment variable to prevent KDE powerdevil from blocking S0i3
mkdir -p %{buildroot}/etc/environment.d
install -m 644 environment.d/50-no-ddcutil.conf %{buildroot}/etc/environment.d/50-cros-ec-no-ddcutil.conf

%post
# Add and build the module with DKMS upon RPM installation
dkms add -m %{name} -v %{version} || :
dkms build -m %{name} -v %{version} || :
dkms install -m %{name} -v %{version} || :

# Add module to modules-load.d, but also add a softdep so it waits for cros_ec_proto
echo "cros_ec_sleep_kprobe" > /etc/modules-load.d/cros-ec-sleep-fix.conf
echo "softdep cros_ec_sleep_kprobe pre: cros_ec_proto" > /etc/modprobe.d/cros_ec_sleep_kprobe.conf

echo "========================================================================="
echo " ChromeOS EC Suspend Failsafe (DKMS) successfully installed."
echo ""
echo " 🛠️  AUTOMATIC SLEEP TWEAKS APPLIED 🛠️"
echo " To ensure your laptop reaches true deep hardware sleep (S0i3), the"
echo " following settings were enabled by default:"
echo ""
echo " 1. Wi-Fi Power Saving (iwlwifi)"
echo "    Why: Intel Wi-Fi cards will keep the CPU awake and block sleep"
echo "    if their power-saving features are disabled."
echo "    To disable this tweak, run:"
echo "    sudo rm /etc/modprobe.d/cros-ec-iwlwifi-s0ix.conf"
echo ""
echo " 2. KDE Powerdevil DDCUtil Bypass"
echo "    Why: KDE Plasma's battery monitor continuously polls external"
echo "    monitors over I2C during suspend, which wakes the hardware bus"
echo "    and breaks deep sleep."
echo "    To disable this tweak, run:"
echo "    sudo rm /etc/environment.d/50-cros-ec-no-ddcutil.conf"
echo "-------------------------------------------------------------------------"

if command -v mokutil >/dev/null && mokutil --sb-state 2>/dev/null | grep -qi "enabled"; then
    echo " ⚠️  SECURE BOOT DETECTED ⚠️"
    echo ""
    echo " DKMS has automatically generated a local Machine Owner Key (MOK) on"
    echo " your machine and signed the new kernel module with it."
    echo ""
    echo " To allow your kernel to load this module, you MUST enroll this locally"
    echo " generated public key into your UEFI firmware."
    echo ""
    echo " Please copy and run the following command in your terminal now:"
    echo ""
    echo "     sudo mokutil --import /var/lib/dkms/mok.pub"
    echo ""
    echo " You will be asked to set a one-time password. After that, REBOOT."
    echo " On the blue pre-boot screen, select 'Enroll MOK' and enter the password."
    echo "========================================================================="
else
    echo " IMPORTANT: You MUST REBOOT your system for the patched kernel module"
    echo " and Wi-Fi power-saving configurations to take effect!"
    echo "========================================================================="
fi

%preun
# Remove the module from DKMS upon RPM uninstallation
if [ "$1" = 0 ]; then
    dkms remove -m %{name} -v %{version} --all || :
    rm -f /etc/modules-load.d/cros-ec-sleep-fix.conf
    rm -f /etc/modprobe.d/cros_ec_sleep_kprobe.conf
fi

%files
/usr/src/%{name}-%{version}/
%config(noreplace) /etc/modprobe.d/cros-ec-iwlwifi-s0ix.conf
%config(noreplace) /etc/environment.d/50-cros-ec-no-ddcutil.conf

%changelog
* Tue Sep 01 2026 Ray X <ray@x-r-c.com> - 1.0-1
- Initial release of the cros-ec-sleep-fix DKMS RPM package.
