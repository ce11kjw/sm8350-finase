// SPDX-License-Identifier: GPL-2.0
// 5.4 兼容桩：原 pkg_observer 依赖 5.9+ fsnotify handle_inode_event
#include <linux/types.h>
#include "klog.h" // IWYU pragma: keep
#include "manager/throne_tracker.h"

int ksu_observer_init(void)
{
    pr_info("pkg_observer: disabled on kernel 5.4 (fsnotify API changed in 5.9)\n");
    return 0;
}

void ksu_observer_exit(void) {}
