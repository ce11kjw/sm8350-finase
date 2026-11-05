#!/usr/bin/env python3
"""
5.4 direct sys_call_table hook backend ("all features" build)

Why: the tracepoint->dispatcher backend rewrites regs->syscallno inside
sys_enter and relies on _TIF_SYSCALL_WORK/syscall_trace_enter returning it.
On 5.4 that path is fragile during early boot (init/system_server), and the
dispatcher slot + x8 juggling is where the first-screen hang comes from.

This replaces the entry path with plain per-syscall table trampolines:
  sys_call_table[nr] = trampoline -> ksu_hook_xxx() -> saved original

No tracepoint is registered, no dispatcher slot is used, and the saved
original is called through ksu_call_original() so there is no recursion.

Run from drivers/kernelsu. Idempotent.
"""
import os
import sys

ok = []
warn = []


def rd(p):
    return open(p, encoding='utf-8', errors='ignore').read()


def wr(p, s):
    open(p, 'w', encoding='utf-8').write(s)


def rep(path, old, new, tag, count=1):
    s = rd(path)
    if new in s and old not in s:
        ok.append(tag + '(already)')
        return
    if old not in s:
        warn.append('%s: anchor not found' % tag)
        return
    s = s.replace(old, new, count)
    wr(path, s)
    ok.append(tag)


# ---------------- 0) pmd_leaf + diag vars (ksu_diag.py is optional) ----------------
P0 = 'hook/arm64/patch_memory.c'
s0 = rd(P0)
if 'define pmd_leaf' not in s0:
    a0 = '#include "asm-generic/fixmap.h"\n'
    if a0 in s0:
        s0 = s0.replace(a0, a0 +
            '\n/* 5.4: pmd_leaf arrived in 5.9; pmd_sect is the equivalent */\n'
            '#ifndef pmd_leaf\n#define pmd_leaf(pmd) pmd_sect(pmd)\n#endif\n', 1)
        wr(P0, s0)
        ok.append('pmd_leaf')
    else:
        warn.append('pmd_leaf: anchor missing')
else:
    ok.append('pmd_leaf(already)')

P0 = 'hook/arm64/syscall_hook.c'
s0 = rd(P0)
if 'int ksu_diag_tbl_ok' not in s0:
    a0 = 'syscall_fn_t *ksu_syscall_table = NULL;\n'
    if a0 in s0:
        s0 = s0.replace(a0, a0 + '\nint ksu_diag_tbl_ok = -1;\nint ksu_diag_disp_ok = -1;\n', 1)
        wr(P0, s0)
        ok.append('diag-vars')
    else:
        warn.append('diag-vars: anchor missing')
else:
    ok.append('diag-vars(already)')

# ---------------- 1) saved-original table + accessor ----------------
P = 'hook/arm64/syscall_hook.c'
rep(P,
    "static DEFINE_MUTEX(hooked_entries_lock);\n",
    "/* direct-table backend: original targets, indexed by syscall nr */\n"
    "static syscall_fn_t ksu_syscall_orig[__NR_syscalls];\n\n"
    "long __nocfi ksu_call_original(int nr, const struct pt_regs *regs)\n"
    "{\n"
    "    if (nr < 0 || nr >= __NR_syscalls || !ksu_syscall_orig[nr])\n"
    "        return -ENOSYS;\n"
    "    return ksu_syscall_orig[nr](regs);\n"
    "}\n\n"
    "static DEFINE_MUTEX(hooked_entries_lock);\n",
    'orig-table')

rep(P,
    "    syscall_fn_t orig = READ_ONCE(ksu_syscall_table[nr]);\n"
    "    if (old)\n",
    "    syscall_fn_t orig = READ_ONCE(ksu_syscall_table[nr]);\n"
    "    ksu_syscall_orig[nr] = orig;\n"
    "    if (old)\n",
    'record-orig')

# dispatcher install -> direct mode
rep(P,
    "    // Find one ni_syscall slot for the dispatcher\n"
    "    if (ksu_find_ni_syscall_slots(&ni_slot, 1) < 1) {\n"
    "        pr_err(\"failed to find ni_syscall slot for dispatcher\\n\");\n"
    "        return -ENOENT;\n"
    "    }\n"
    "\n"
    "    ksu_dispatcher_nr = ni_slot;\n"
    "    ksu_syscall_table_hook(ksu_dispatcher_nr, (syscall_fn_t)ksu_syscall_dispatcher, NULL);\n"
    "    if (READ_ONCE(ksu_syscall_table[ksu_dispatcher_nr]) != (syscall_fn_t)ksu_syscall_dispatcher) {\n"
    "        ksu_dispatcher_nr = -1;\n"
    "        return -EIO;\n"
    "    }\n"
    "    ksu_diag_disp_ok = 0;\n"
    "    pr_info(\"dispatcher installed at slot %d\\n\", ksu_dispatcher_nr);\n"
    "    return 0;\n"
    "}",
    "#ifdef KSU_DIRECT_TABLE_HOOK\n"
    "    (void)ni_slot;\n"
    "    ksu_dispatcher_nr = -1;\n"
    "    ksu_diag_disp_ok = -3; /* direct sys_call_table hooks */\n"
    "    pr_info(\"ksu: direct sys_call_table hook mode\\n\");\n"
    "    return 0;\n"
    "#else\n"
    "    // Find one ni_syscall slot for the dispatcher\n"
    "    if (ksu_find_ni_syscall_slots(&ni_slot, 1) < 1) {\n"
    "        pr_err(\"failed to find ni_syscall slot for dispatcher\\n\");\n"
    "        return -ENOENT;\n"
    "    }\n"
    "\n"
    "    ksu_dispatcher_nr = ni_slot;\n"
    "    ksu_syscall_table_hook(ksu_dispatcher_nr, (syscall_fn_t)ksu_syscall_dispatcher, NULL);\n"
    "    if (READ_ONCE(ksu_syscall_table[ksu_dispatcher_nr]) != (syscall_fn_t)ksu_syscall_dispatcher) {\n"
    "        ksu_dispatcher_nr = -1;\n"
    "        return -EIO;\n"
    "    }\n"
    "    ksu_diag_disp_ok = 0;\n"
    "    pr_info(\"dispatcher installed at slot %d\\n\", ksu_dispatcher_nr);\n"
    "    return 0;\n"
    "#endif\n"
    "}",
    'direct-mode')

# ---------------- 2) header ----------------
P = 'hook/syscall_hook.h'
s = rd(P)
if 'ksu_call_original' not in s:
    s = s.replace('#include <asm/syscall.h>',
                  '#include <asm/syscall.h>\n#include <linux/version.h>', 1)
    s = s.replace("void ksu_syscall_table_hook(int nr, syscall_fn_t fn, syscall_fn_t *old);",
                  "void ksu_syscall_table_hook(int nr, syscall_fn_t fn, syscall_fn_t *old);\n"
                  "long ksu_call_original(int nr, const struct pt_regs *regs);", 1)
    s = s.replace("#include <linux/version.h>",
                  "#include <linux/version.h>\n"
                  "\n"
                  "/* < 5.7: no syscall_work flags; use direct sys_call_table hooks */\n"
                  "#if defined(__aarch64__) && LINUX_VERSION_CODE < KERNEL_VERSION(5, 7, 0)\n"
                  "#define KSU_DIRECT_TABLE_HOOK 1\n"
                  "#endif\n", 1)
    wr(P, s)
    ok.append('header')
else:
    ok.append('header(already)')

# ---------------- 3) hooks must call the saved original ----------------
for P in ('feature/sucompat.c', 'hook/syscall_event_bridge.c'):
    s = rd(P)
    n = s.count('ksu_syscall_table[orig_nr](regs)')
    s = s.replace('ksu_syscall_table[orig_nr](regs)', 'ksu_call_original(orig_nr, regs)')
    m = s.count('ksu_syscall_table[__NR_execveat](regs)')
    s = s.replace('ksu_syscall_table[__NR_execveat](regs)', 'ksu_call_original(__NR_execveat, regs)')
    wr(P, s)
    ok.append('%s(orig:%d,execveat:%d)' % (os.path.basename(P), n, m))

# ---------------- 4) manager: direct registration ----------------
P = 'hook/syscall_hook_manager.c'
rep(P,
    "#ifdef MODULE\nstatic bool syscall_redirects_pinned_module;\n#endif\n",
    "#ifdef KSU_DIRECT_TABLE_HOOK\n"
    "static long __nocfi ksu_tbl_setresuid(const struct pt_regs *regs)\n"
    "{ return ksu_hook_setresuid(__NR_setresuid, regs); }\n"
    "static long __nocfi ksu_tbl_execve(const struct pt_regs *regs)\n"
    "{ return ksu_hook_execve(__NR_execve, regs); }\n"
    "static long __nocfi ksu_tbl_execveat(const struct pt_regs *regs)\n"
    "{ return ksu_hook_execveat(__NR_execveat, regs); }\n"
    "static long __nocfi ksu_tbl_newfstatat(const struct pt_regs *regs)\n"
    "{ return ksu_hook_newfstatat(__NR_newfstatat, regs); }\n"
    "static long __nocfi ksu_tbl_faccessat(const struct pt_regs *regs)\n"
    "{ return ksu_hook_faccessat(__NR_faccessat, regs); }\n"
    "#endif\n"
    "\n"
    "#ifdef MODULE\nstatic bool syscall_redirects_pinned_module;\n#endif\n",
    'manager-wrappers')

rep(P,
    "    if (!ksu_syscall_table || ksu_dispatcher_nr < 0) {\n"
    "        pr_err(\"hook_manager: syscall dispatcher is unavailable\\n\");\n"
    "        return -ENOENT;\n"
    "    }\n",
    "#ifdef KSU_DIRECT_TABLE_HOOK\n"
    "    if (!ksu_syscall_table) {\n"
    "        pr_err(\"hook_manager: sys_call_table is unavailable\\n\");\n"
    "        return -ENOENT;\n"
    "    }\n"
    "#else\n"
    "    if (!ksu_syscall_table || ksu_dispatcher_nr < 0) {\n"
    "        pr_err(\"hook_manager: syscall dispatcher is unavailable\\n\");\n"
    "        return -ENOENT;\n"
    "    }\n"
    "#endif\n",
    'manager-guard')

pairs = [
    ('setresuid', '__NR_setresuid', 'ksu_hook_setresuid', 'ksu_tbl_setresuid'),
    ('execve', '__NR_execve', 'ksu_hook_execve', 'ksu_tbl_execve'),
    ('execveat', '__NR_execveat', 'ksu_hook_execveat', 'ksu_tbl_execveat'),
    ('newfstatat', '__NR_newfstatat', 'ksu_hook_newfstatat', 'ksu_tbl_newfstatat'),
    ('faccessat', '__NR_faccessat', 'ksu_hook_faccessat', 'ksu_tbl_faccessat'),
]
for tag, nr, fn, wrap in pairs:
    old = ("    err = ksu_register_syscall_hook(%s, %s);\n"
           "    if (err)\n"
           "        ret = err;\n") % (nr, fn)
    new = ("#ifdef KSU_DIRECT_TABLE_HOOK\n"
           "    ksu_syscall_table_hook(%s, (syscall_fn_t)%s, NULL);\n"
           "#else\n"
           "    err = ksu_register_syscall_hook(%s, %s);\n"
           "    if (err)\n"
           "        ret = err;\n"
           "#endif\n") % (nr, wrap, nr, fn)
    rep(P, old, new, 'reg-' + tag)

rep(P,
    "#ifdef CONFIG_HAVE_SYSCALL_TRACEPOINTS\n    err = register_trace_prio_sys_enter(",
    "#if !defined(KSU_DIRECT_TABLE_HOOK) && defined(CONFIG_HAVE_SYSCALL_TRACEPOINTS)\n"
    "    err = register_trace_prio_sys_enter(",
    'tp-reg')

rep(P,
    "#ifdef CONFIG_HAVE_SYSCALL_TRACEPOINTS\n    unregister_trace_sys_enter(",
    "#if !defined(KSU_DIRECT_TABLE_HOOK) && defined(CONFIG_HAVE_SYSCALL_TRACEPOINTS)\n"
    "    unregister_trace_sys_enter(",
    'tp-unreg')

# under SUSFS the setresuid hook is normally left to the SUSFS kernel patch;
# kernel-5.4's patch has no such call site, so keep our table hook active
rep(P,
    "#ifndef CONFIG_KSU_SUSFS\n#ifdef KSU_DIRECT_TABLE_HOOK\n    ksu_syscall_table_hook(__NR_setresuid",
    "#if !defined(CONFIG_KSU_SUSFS) || defined(KSU_DIRECT_TABLE_HOOK)\n"
    "#ifdef KSU_DIRECT_TABLE_HOOK\n    ksu_syscall_table_hook(__NR_setresuid",
    'setresuid-susfs')

# direct mode must not clear the routing table before table restore
rep(P,
    "#ifndef CONFIG_KSU_SUSFS\n    ksu_unregister_syscall_hook(__NR_setresuid);\n#endif\n",
    "#if !defined(KSU_DIRECT_TABLE_HOOK) && !defined(CONFIG_KSU_SUSFS)\n"
    "    ksu_unregister_syscall_hook(__NR_setresuid);\n#endif\n",
    'unreg-setresuid')

print('[direct-hooks] ok:', ', '.join(ok))
if warn:
    print('[direct-hooks] WARN:', '; '.join(warn))
    sys.exit(1)
