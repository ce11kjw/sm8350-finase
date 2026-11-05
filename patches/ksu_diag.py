#!/usr/bin/env python3
"""
5.4 关键修复 + 诊断节点
1) patch_memory.c: 补 pmd_leaf（5.4 只有 pmd_sect），否则 2MB 块映射的
   sys_call_table 无法转换物理地址 -> syscall dispatcher 装不上 -> 管理器"不支持"
2) 增加 /proc/ksu_diag（0444），把初始化结果暴露给 shell
"""
import os, sys

def rd(p):
    return open(p, encoding='utf-8', errors='ignore').read()

def wr(p, s):
    open(p, 'w', encoding='utf-8').write(s)

ok = []

# ---------- 1) pmd_leaf 兼容 ----------
p = 'hook/arm64/patch_memory.c'
s = rd(p)
if 'define pmd_leaf' not in s:
    anchor = '#include "asm-generic/fixmap.h"\n'
    assert anchor in s, 'patch_memory.c: 找不到 fixmap include'
    s = s.replace(anchor, anchor +
                  '\n/* 5.4: pmd_leaf 在 5.9 才有，用 pmd_sect 等价替代 */\n'
                  '#ifndef pmd_leaf\n#define pmd_leaf(pmd) pmd_sect(pmd)\n#endif\n', 1)
    wr(p, s)
    ok.append('pmd_leaf')

# ---------- 2) 诊断变量 ----------
p = 'hook/arm64/syscall_hook.c'
s = rd(p)
if 'ksu_diag_tbl_ok' not in s:
    anchor = 'int __init ksu_syscall_table_init(void)\n{\n'
    assert anchor in s, 'syscall_hook.c: 找不到 table_init'
    s = s.replace(anchor, 'int ksu_diag_tbl_ok = -1;\n\n' + anchor, 1)
    s = s.replace('    if (!ksu_syscall_table)\n        return -ENOENT;\n\n    return 0;\n}',
                  '    if (!ksu_syscall_table) {\n        ksu_diag_tbl_ok = -1;\n        return -ENOENT;\n    }\n    ksu_diag_tbl_ok = 0;\n    return 0;\n}', 1)
    wr(p, s)
    ok.append('diag_tbl')

# 记录 dispatcher 是否装好
p = 'hook/arm64/syscall_hook.c'
s = rd(p)
if 'ksu_diag_disp_ok' not in s:
    s = s.replace('int ksu_diag_tbl_ok = -1;', 'int ksu_diag_tbl_ok = -1;\nint ksu_diag_disp_ok = -1;', 1)
    s = s.replace('    pr_info("dispatcher installed at slot %d\\n", ksu_dispatcher_nr);\n    return 0;',
                  '    ksu_diag_disp_ok = 0;\n    pr_info("dispatcher installed at slot %d\\n", ksu_dispatcher_nr);\n    return 0;', 1)
    wr(p, s)
    ok.append('diag_disp')

# 记录 reboot kprobe 结果
p = 'supercall/supercall.c'
s = rd(p)
if 'ksu_diag_reboot_rc' not in s:
    s = s.replace('void __init ksu_supercalls_init(void)\n{',
                  'int ksu_diag_reboot_rc = -1;\n\nvoid __init ksu_supercalls_init(void)\n{', 1)
    s = s.replace('    rc = register_kprobe(&reboot_kp);',
                  '    rc = register_kprobe(&reboot_kp);\n    ksu_diag_reboot_rc = rc;', 1)
    # 追加诊断节点
    s += r'''

/* ===== 诊断节点：/proc/ksu_diag (0444) ===== */
#include <linux/proc_fs.h>
#include <linux/seq_file.h>
#include <linux/init.h>

extern int ksu_dispatcher_nr;
extern bool ksu_hook_backend_ready;
extern int ksu_diag_tbl_ok;
extern int ksu_diag_disp_ok;
extern bool ksu_late_loaded;

static int ksu_diag_show(struct seq_file *m, void *v)
{
    seq_printf(m, "sys_call_table=%s\n", ksu_diag_tbl_ok == 0 ? "ok" : "FAIL");
    seq_printf(m, "dispatcher=%s nr=%d\n", ksu_diag_disp_ok == 0 ? "ok" : "FAIL", ksu_dispatcher_nr);
    seq_printf(m, "reboot_kprobe_rc=%d\n", ksu_diag_reboot_rc);
    seq_printf(m, "backend_ready=%d\n", ksu_hook_backend_ready);
    seq_printf(m, "late_loaded=%d\n", ksu_late_loaded);
    return 0;
}

static int ksu_diag_open(struct inode *inode, struct file *file)
{
    return single_open(file, ksu_diag_show, NULL);
}

static const struct file_operations ksu_diag_fops = {
    .open = ksu_diag_open,
    .read = seq_read,
    .llseek = seq_lseek,
    .release = single_release,
};

static int __init ksu_diag_init(void)
{
    proc_create("ksu_diag", 0444, NULL, &ksu_diag_fops);
    return 0;
}
late_initcall(ksu_diag_init);
'''
    wr(p, s)
    ok.append('diag_node')

print('[ksu-diag] 完成:', ', '.join(ok) if ok else '无需改动')
