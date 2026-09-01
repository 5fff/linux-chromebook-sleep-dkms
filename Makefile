obj-m := cros_ec_sleep_kprobe.o

# DKMS sets KERNELRELEASE during its build process.
# If KERNELRELEASE is not set, fallback to uname -r for manual builds.
KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean
