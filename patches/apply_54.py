#!/usr/bin/env python3
"""FinaSU -> Linux 5.4 移植补丁（在 kernel 源码根目录执行）"""
import os

K = 'drivers/kernelsu'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, 'patches')

def read(p):
    return open(p, encoding='utf-8', errors='ignore').read()

def write(p, s):
    open(p, 'w', encoding='utf-8').write(s)

# 1) rules.c 换 5.4 版
write(f'{K}/selinux/rules.c', read(os.path.join(P, 'rules_54.c')))
print('[apply54] rules.c replaced')

# 2) selinux_hide.c 换成桩
write(f'{K}/feature/selinux_hide.c', read(os.path.join(P, 'selinux_hide_stub.c')))
print('[apply54] selinux_hide.c stubbed')

# 3) 删除 sepolicy.c 里两个 5.7 专属函数
def drop_func(src, header):
    i = src.find(header)
    if i < 0:
        return src, False
    j = src.find('{', i)
    depth, k = 0, j
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                break
        k += 1
    end = k + 1
    while end < len(src) and src[end] == '\n':
        end += 1
    return src[:i] + src[end:], True

p = f'{K}/selinux/sepolicy.c'
s = read(p)
for h in ('void ksu_destroy_sepolicy(', 'struct selinux_policy *ksu_dup_sepolicy('):
    s, ok = drop_func(s, h)
    print(f'[apply54] drop {h.strip()} -> {ok}')
write(p, s)

# 4) sepolicy.h 去掉声明
p = f'{K}/selinux/sepolicy.h'
s = read(p)
write(p, ''.join(l for l in s.splitlines(True)
                 if 'ksu_dup_sepolicy' not in l and 'ksu_destroy_sepolicy' not in l))
print('[apply54] sepolicy.h cleaned')

# 5) ksu.h 去掉 backup_sepolicy 声明
p = f'{K}/include/ksu.h'
s = read(p)
write(p, ''.join(l for l in s.splitlines(True) if 'selinux_policy *backup_sepolicy' not in l))
print('[apply54] ksu.h cleaned')
print('[apply54] DONE')
