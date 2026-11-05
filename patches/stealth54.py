#!/usr/bin/env python3
"""Kernel-side stealth tweaks for kernel 5.4 builds.

Applied from the kernel tree after features54.py.
"""
import sys

ok = []
warn = []

p = 'drivers/kernelsu/core/init.c'
s = open(p, encoding='utf-8').read()

old = """#ifdef MODULE
#ifndef CONFIG_KSU_DEBUG
    kobject_del(&THIS_MODULE->mkobj.kobj);
#endif
#endif
"""

new = """#ifndef CONFIG_KSU_DEBUG
    /*
     * Built-in builds still register /sys/module/kernelsu because the driver
     * declares module_param*. Drop the kobject so app-side scanners looking
     * for root frameworks cannot see it. state_in_sysfs guards LKM builds and
     * kernels where the kobject was never registered.
     */
    if (THIS_MODULE && THIS_MODULE->mkobj.kobj.state_in_sysfs)
        kobject_del(&THIS_MODULE->mkobj.kobj);
#endif
"""

if new.strip() not in s:
    if old not in s:
        warn.append('init.c: kobject_del anchor missing')
    else:
        s = s.replace(old, new, 1)
        open(p, 'w', encoding='utf-8').write(s)
        ok.append('init.c:kobject_del')
else:
    ok.append('init.c(already)')

print('[stealth54] ok:', ', '.join(ok))
if warn:
    print('[stealth54] WARN:', '; '.join(warn))
    sys.exit(1)
