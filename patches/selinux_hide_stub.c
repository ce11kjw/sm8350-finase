// SPDX-License-Identifier: GPL-2.0
// 5.4 兼容桩：原实现依赖 5.7+ 的 struct selinux_policy / sidtab API
// 本平台上禁用「伪造 SELinux 状态」功能，root 功能不受影响
#include <linux/types.h>
#include <linux/kernel.h>
#include "klog.h" // IWYU pragma: keep
#include "feature/selinux_hide.h"

bool ksu_selinux_hide_enabled __read_mostly = false;
bool ksu_selinux_hide_running __read_mostly = false;

void ksu_selinux_hide_init(void)
{
    pr_info("selinux_hide: disabled on kernel 5.4 (needs 5.7+ selinux_policy)\n");
}

void ksu_selinux_hide_exit(void) {}

void ksu_selinux_hide_drop_backup_if_unused(void) {}

void ksu_selinux_hide_handle_second_stage(void) {}

void ksu_selinux_hide_handle_post_fs_data(void) {}
