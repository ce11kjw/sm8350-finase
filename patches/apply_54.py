#!/usr/bin/env python3
"""FinaSU -> Linux 5.4 移植补丁（在 kernel 源码根目录执行）"""
import os

K = 'drivers/kernelsu'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'patches')

def read(p): return open(p, encoding='utf-8', errors='ignore').read()
def write(p, s): open(p, 'w', encoding='utf-8').write(s)

# 0) 补齐 5.4 里不存在但 FinaSU 引用的内核头（转发到 kernel.h / asm/pgtable.h）
SHIMS = {
    'linux/pgtable.h': '#include <asm/pgtable.h>\n',
    'linux/minmax.h': '#include <linux/kernel.h>\n',
    'linux/hex.h': '#include <linux/kernel.h>\n',
}
for name, body in SHIMS.items():
    p = f'include/{name}'
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write(p, '/* 5.4 compat shim */\n' + body)
        print(f'[apply54] shim {name}')

# 1) rules.c：改成 5.4 的 ss->policydb 路径
write(f'{K}/selinux/rules.c', read(os.path.join(P, 'rules_54.c')))
print('[apply54] rules.c replaced')

# 2) selinux_hide.c：换成桩（原实现依赖 5.7+ selinux_policy/sidtab）
write(f'{K}/feature/selinux_hide.c', read(os.path.join(P, 'selinux_hide_stub.c')))
print('[apply54] selinux_hide.c stubbed')

# 3) sepolicy.c：换 5.4 版并删除两个 5.7 专属函数
p = f'{K}/selinux/sepolicy.c'
s = read(os.path.join(P, 'sepolicy_54.c'))

def drop_func(src, header):
    i = src.find(header)
    if i < 0:
        return src, False
    j = src.find('{', i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{': depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0: break
        k += 1
    end = k + 1
    while end < len(src) and src[end] == '\n': end += 1
    return src[:i] + src[end:], True

for h in ('void ksu_destroy_sepolicy(', 'struct selinux_policy *ksu_dup_sepolicy('):
    s, ok = drop_func(s, h)
    print(f'[apply54] drop {h.strip()} -> {ok}')
write(p, s)

# 4) sepolicy.h：去掉两个声明
p = f'{K}/selinux/sepolicy.h'
s = read(p)
write(p, ''.join(l for l in s.splitlines(True)
                 if 'ksu_dup_sepolicy' not in l and 'ksu_destroy_sepolicy' not in l))
print('[apply54] sepolicy.h cleaned')

# 5) ksu.h：去掉 backup_sepolicy 声明
p = f'{K}/include/ksu.h'
s = read(p)
write(p, ''.join(l for l in s.splitlines(True) if 'selinux_policy *backup_sepolicy' not in l))
print('[apply54] ksu.h cleaned')

# 5.5) 补齐 sched 相关头
RULES = [
    (('tasklist_lock', 'task_pgrp', 'task_session'), 'linux/sched/signal.h'),
    (('init_task',), 'linux/sched.h'),
    (('put_task_struct', 'get_task_struct'), 'linux/sched/task.h'),
]
import glob
for names, hdr in RULES:
    for f in glob.glob(f'{K}/**/*.c', recursive=True):
        t = read(f)
        if hdr in t:
            continue
        if any(n in t for n in names):
            write(f, f'#include <{hdr}>\n' + t)
            print(f'[apply54] +{hdr} -> {f}')

# 6) 自检
leftover = 0
for dp, _, fs in os.walk(K):
    for f in fs:
        if f.endswith(('.c', '.h')):
            t = read(os.path.join(dp, f))
            if 'selinux_policy' in t:
                leftover += 1
                print(f'[apply54] WARN still refs selinux_policy: {os.path.join(dp,f)}')
print(f'[apply54] DONE (selinux_policy 残留文件数: {leftover})')
