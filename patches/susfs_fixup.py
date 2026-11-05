#!/usr/bin/env python3
"""SUSFS 5.4 补丁的 3 处手工修复（在 kernel 根目录执行）"""
import sys

def rd(p):
    return open(p, encoding='utf-8', errors='ignore').read()

def wr(p, s):
    open(p, 'w', encoding='utf-8').write(s)

ok = []

# 1) include/linux/mount.h : vfsmount 里加 susfs_mnt_id_backup
p = 'include/linux/mount.h'
s = rd(p)
if 'susfs_mnt_id_backup' not in s:
    old = "\tANDROID_KABI_RESERVE(4);\n\tvoid *data;"
    new = ("#ifdef CONFIG_KSU_SUSFS\n"
           "\tANDROID_KABI_USE(4, u64 susfs_mnt_id_backup);\n"
           "#else\n"
           "\tANDROID_KABI_RESERVE(4);\n"
           "#endif\n\tvoid *data;")
    if old in s:
        wr(p, s.replace(old, new, 1)); ok.append('mount.h')
    else:
        print('[fixup] mount.h 未找到锚点'); sys.exit(1)

# 2) fs/proc/task_mmu.c : include + extern + show_map_vma 的 SUS_KSTAT
p = 'fs/proc/task_mmu.c'
s = rd(p)
if 'susfs_def.h' not in s:
    anchor = "#include <linux/pkeys.h>\n"
    add = anchor + "#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n#include <linux/susfs_def.h>\n#endif\n"
    s = s.replace(anchor, add, 1); ok.append('task_mmu-include')
if 'susfs_sus_ino_for_show_map_vma' not in s:
    anchor = "static void\nshow_map_vma(struct seq_file *m"
    add = ("#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n"
           "extern void susfs_sus_ino_for_show_map_vma(unsigned long ino, dev_t *out_dev, unsigned long *out_ino);\n"
           "#endif\n\n") + anchor
    s = s.replace(anchor, add, 1); ok.append('task_mmu-extern')
    old = ("\t\tdev = inode->i_sb->s_dev;\n"
           "\t\tino = inode->i_ino;\n")
    new = ("#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n"
           "\t\tif (unlikely(inode->i_state & INODE_STATE_SUS_KSTAT)) {\n"
           "\t\t\tsusfs_sus_ino_for_show_map_vma(inode->i_ino, &dev, &ino);\n"
           "\t\t\tgoto bypass_orig_flow;\n"
           "\t\t}\n"
           "#endif\n"
           "\t\tdev = inode->i_sb->s_dev;\n"
           "\t\tino = inode->i_ino;\n"
           "#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT\n"
           "bypass_orig_flow:\n"
           "#endif\n")
    if old in s:
        s = s.replace(old, new, 1); ok.append('task_mmu-body')
wr(p, s)

# 3) fs/proc/fd.c : SUS_MOUNT 的 mnt_id 伪装
p = 'fs/proc/fd.c'
s = rd(p)
if 'susfs_task_state' not in s:
    anchor = ("\tseq_printf(m, \"pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\n\",\n"
              "\t\t   (long long)file->f_pos, f_flags,\n"
              "\t\t   real_mount(file->f_path.mnt)->mnt_id);\n")
    new = ("#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n"
           "\tmnt = real_mount(file->f_path.mnt);\n"
           "\tif (likely(current->susfs_task_state & TASK_STRUCT_NON_ROOT_USER_APP_PROC) &&\n"
           "\t\t\tmnt->mnt_id >= DEFAULT_SUS_MNT_ID) {\n"
           "\t\tstruct path path;\n"
           "\t\tchar *pathname = kmalloc(PAGE_SIZE, GFP_KERNEL);\n"
           "\t\tchar *dpath;\n"
           "\t\tfor (; mnt->mnt_id >= DEFAULT_SUS_MNT_ID; mnt = mnt->mnt_parent) { }\n"
           "\t\tif (!pathname)\n"
           "\t\t\tgoto out_seq_printf;\n"
           "\t\tdpath = d_path(&file->f_path, pathname, PAGE_SIZE);\n"
           "\t\tif (!dpath)\n"
           "\t\t\tgoto out_free_pathname;\n"
           "\t\tif (kern_path(dpath, 0, &path))\n"
           "\t\t\tgoto out_free_pathname;\n"
           "\t\tseq_printf(m, \"pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\nino:\\t%lu\\n\",\n"
           "\t\t\t\t(long long)file->f_pos, f_flags,\n"
           "\t\t\t\tmnt->mnt_id, path.dentry->d_inode->i_ino);\n"
           "\t\tpath_put(&path);\n"
           "\t\tkfree(pathname);\n"
           "\t\tgoto bypass_orig_flow;\n"
           "out_free_pathname:\n"
           "\t\tkfree(pathname);\n"
           "\t}\n"
           "out_seq_printf:\n"
           "\tseq_printf(m, \"pos:\\t%lli\\nflags:\\t0%o\\nmnt_id:\\t%i\\nino:\\t%lu\\n\",\n"
           "\t\t   (long long)file->f_pos, f_flags,\n"
           "\t\t   mnt->mnt_id, file_inode(file)->i_ino);\n"
           "bypass_orig_flow:\n"
           "#else\n" + anchor + "#endif\n")
    if anchor in s:
        s = s.replace(anchor, new, 1); ok.append('fd.c')
    else:
        print('[fixup] fd.c 未找到锚点（继续）')
    # 声明 mnt 变量
    if 'struct mount *mnt = NULL;' not in s:
        a2 = "\tstruct task_struct *task;\n"
        s = s.replace(a2, a2 + "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n\tstruct mount *mnt = NULL;\n#endif\n", 1)
        ok.append('fd.c-var')
    # 头文件
    if 'susfs_def.h' not in s:
        a3 = "#include <linux/proc_fs.h>\n"
        s = s.replace(a3, a3 + "#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n#include <linux/susfs_def.h>\n#endif\n", 1)
        ok.append('fd.c-include')
wr(p, s)


# 4) fs/proc/cmdline.c : 5.4 没有 /proc/bootconfig，改挂到 /proc/cmdline
p = 'fs/proc/cmdline.c'
try:
    s = rd(p)
    if 'susfs_spoof_cmdline_or_bootconfig' not in s:
        s = s.replace(
            "#include <linux/seq_file.h>\n",
            "#include <linux/seq_file.h>\n"
            "#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n"
            "#include <linux/susfs_def.h>\n"
            "extern int susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);\n"
            "#endif\n", 1)
        s = s.replace(
            "static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n",
            "static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n"
            "#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n"
            "\tif (!susfs_spoof_cmdline_or_bootconfig(m))\n"
            "\t\treturn 0;\n"
            "#endif\n", 1)
        wr(p, s)
        ok.append('cmdline.c(5.4适配)')
except FileNotFoundError:
    print('[fixup] cmdline.c 不存在，跳过')


# 5) include/linux/susfs_def.h : 补齐 FinaSU 期望的 13 个新一代接口
p = 'include/linux/susfs_def.h'
s = rd(p)
if 'SUSFS_COMPAT54_H' not in s:
    s += r"""
/* ===== 5.4 兼容层：补齐 FinaSU 期望但 kernel-5.4 SUSFS 未提供的接口 ===== */
#ifndef SUSFS_COMPAT54_H
#define SUSFS_COMPAT54_H
#include <linux/sched.h>

#ifndef TASK_STRUCT_NO_SU_PROC
#define TASK_STRUCT_NO_SU_PROC BIT(25)
#endif

/* 真实实现：per-task 标记 */
static inline void susfs_set_current_proc_no_su(void)
{
	current->susfs_task_state |= TASK_STRUCT_NO_SU_PROC;
}
static inline bool susfs_is_current_proc_no_su(void)
{
	return !!(current->susfs_task_state & TASK_STRUCT_NO_SU_PROC);
}
static inline void susfs_set_current_proc_umounted(void)
{
	current->susfs_task_state |= TASK_STRUCT_NON_ROOT_USER_APP_PROC;
}
static inline void susfs_set_current_proc_umounted_for_zygote_next(void) { }

/* 以下功能在 kernel-5.4 的 SUSFS 中不存在，空实现 */
static inline void susfs_add_sus_map(void *arg) { }
static inline void susfs_add_sus_path_loop(void *arg) { }
static inline void susfs_enable_log(void *arg) { }
static inline void susfs_get_enabled_features(void *arg) { }
static inline void susfs_set_avc_log_spoofing(void *arg) { }
static inline void susfs_set_hide_sus_mnts_for_non_su_procs(void *arg) { }
static inline void susfs_show_variant(void *arg) { }
static inline void susfs_show_version(void *arg) { }
static inline void susfs_start_sdcard_monitor_fn(void) { }
#endif
"""
    wr(p, s)
    ok.append('susfs_def.h 兼容层(13项)')


# 6) susfs_def.h 补缺失命令号 + 新建类型转换头 + 引入
p = 'include/linux/susfs_def.h'
s = rd(p)
if 'CMD_SUSFS_ADD_SUS_MAP' not in s:
    s += r"""
/* ===== 5.4 补：新版 SUSFS 的命令号与 magic ===== */
#ifndef SUSFS_MAGIC
#define SUSFS_MAGIC 0xFAFAFAFA
#endif
#ifndef CMD_SUSFS_ADD_SUS_PATH_LOOP
#define CMD_SUSFS_ADD_SUS_PATH_LOOP 0x55553
#endif
#ifndef CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS
#define CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS 0x55561
#endif
#ifndef CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING
#define CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING 0x60010
#endif
#ifndef CMD_SUSFS_ADD_SUS_MAP
#define CMD_SUSFS_ADD_SUS_MAP 0x60020
#endif
"""
    wr(p, s); ok.append('susfs_def.h 命令号')

# 类型转换头（只被 FinaSU 的 extension/susfs.c 使用）
hc = 'drivers/kernelsu/extension/susfs_compat54.h'
import os
os.makedirs(os.path.dirname(hc), exist_ok=True)
if not os.path.exists(hc):
    wr(hc, r"""/* 5.4: FinaSU 使用新版 SUSFS 接口，这里把 void __user* 转成 5.4 期望的结构指针 */
#ifndef KSU_SUSFS_COMPAT54_H
#define KSU_SUSFS_COMPAT54_H

#define susfs_add_sus_path(a)              susfs_add_sus_path((struct st_susfs_sus_path __user *)(a))
#define susfs_add_sus_path_loop(a)         susfs_add_sus_path((struct st_susfs_sus_path __user *)(a))
#define susfs_add_sus_mount(a)             susfs_add_sus_mount((struct st_susfs_sus_mount __user *)(a))
#define susfs_add_sus_kstat(a)             susfs_add_sus_kstat((struct st_susfs_sus_kstat __user *)(a))
#define susfs_update_sus_kstat(a)          susfs_update_sus_kstat((struct st_susfs_sus_kstat __user *)(a))
#define susfs_add_try_umount(a)            susfs_add_try_umount((struct st_susfs_try_umount __user *)(a))
#define susfs_set_uname(a)                 susfs_set_uname((struct st_susfs_uname __user *)(a))
#define susfs_add_open_redirect(a)         susfs_add_open_redirect((struct st_susfs_open_redirect __user *)(a))
#define susfs_set_cmdline_or_bootconfig(a) susfs_set_cmdline_or_bootconfig((char __user *)(a))
#define susfs_enable_log(a)                susfs_set_log(!!(a))

#endif
""")
    ok.append('susfs_compat54.h')

# 在 extension/susfs.c 里引入
p = 'drivers/kernelsu/extension/susfs.c'
try:
    s = rd(p)
    if 'susfs_compat54.h' not in s:
        s = s.replace('#include <linux/susfs_def.h>\n',
                      '#include <linux/susfs_def.h>\n#include "extension/susfs_compat54.h"\n', 1)
        wr(p, s); ok.append('susfs.c 引入转换头')
except FileNotFoundError:
    pass

print('[susfs-fixup] 完成:', ', '.join(ok))
