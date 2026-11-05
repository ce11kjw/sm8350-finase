#!/usr/bin/env python3
"""5.4 built-in feature wiring: selinux_hide, pkg_observer, NoMount.

Runs inside the kernel tree, after apply_54.py and the hook patches.
"""
import os
import shutil
import sys

P = sys.argv[1] if len(sys.argv) > 1 else '/data/local/tmp/patches'
K = 'drivers/kernelsu'
ok = []
warn = []

# ---------------------------------------------------------------- 1) sources
shutil.copyfile(f'{P}/selinux_hide_54.c', f'{K}/feature/selinux_hide.c')
ok.append('selinux_hide.c')
shutil.copyfile(f'{P}/pkg_observer_54.c', f'{K}/manager/pkg_observer.c')
ok.append('pkg_observer.c')

# ---------------------------------------------------------------- 2) sepolicy.h
p = f'{K}/selinux/sepolicy.h'
s = open(p, encoding='utf-8').read()
if 'ksu_selinux_policy_54' not in s:
    s = '#include <linux/version.h>\n\n' + s
    s += r'''

/* ==== ksu_selinux_policy_54 ==== */
#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 7, 0)
struct sidtab;

/*
 * 5.4 has no struct selinux_policy (introduced in 5.7). The backup policy for
 * selinux_hide is a private carrier: its policydb is a deep copy of the
 * pristine policy and its sidtab only holds initial SIDs.
 */
struct selinux_policy {
    struct sidtab *sidtab;
    struct policydb policydb;
    u32 latest_granting;
};

struct selinux_policy *ksu_dup_sepolicy(struct policydb *old_db);
void ksu_destroy_sepolicy(struct selinux_policy *pol);
#endif
'''
    open(p, 'w', encoding='utf-8').write(s)
    ok.append('sepolicy.h')
else:
    ok.append('sepolicy.h(already)')

# ---------------------------------------------------------------- 3) NoMount
src = '/tmp/finasu/userspace/nomount/kernel/src'
dst = 'fs/nomount'
if not os.path.isdir(src):
    warn.append('nomount source missing: ' + src)
else:
    shutil.copytree(src, dst, dirs_exist_ok=True)
    ok.append('fs/nomount')

    mk = 'fs/Makefile'
    s = open(mk, encoding='utf-8').read()
    if 'nomount' not in s:
        if not s.endswith('\n'):
            s += '\n'
        s += '\nobj-$(CONFIG_NOMOUNT) += nomount/\n'
        open(mk, 'w', encoding='utf-8').write(s)
        ok.append('fs/Makefile')

    kc = 'fs/Kconfig'
    s = open(kc, encoding='utf-8').read()
    if 'fs/nomount/Kconfig' not in s:
        i = s.rfind('\nendmenu')
        if i < 0:
            warn.append('fs/Kconfig: no endmenu')
        else:
            s = s[:i] + '\nsource "fs/nomount/Kconfig"' + s[i:]
            open(kc, 'w', encoding='utf-8').write(s)
            ok.append('fs/Kconfig')

# ---------------------------------------------------------------- 4) report
for f in ('feature/selinux_hide.c', 'manager/pkg_observer.c'):
    p = f'{K}/{f}'
    print('[features54] %-28s %d bytes' % (f, os.path.getsize(p)))
print('[features54] ok:', ', '.join(ok))
if warn:
    print('[features54] WARN:', '; '.join(warn))
    sys.exit(1)
