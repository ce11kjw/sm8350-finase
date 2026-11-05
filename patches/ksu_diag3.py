#!/usr/bin/env python3
"""
5.4 定位实验：
- 保留 dispatcher 与 execve 钩子
- 去掉 newfstatat / faccessat 的 sucompat 钩子（怀疑它们在 5.4 上不调原 syscall -> 开机卡死）
"""
def rd(p):
    return open(p, encoding='utf-8', errors='ignore').read()

def wr(p, s):
    open(p, 'w', encoding='utf-8').write(s)

ok = []
p = 'hook/syscall_hook_manager.c'
s = rd(p)

for nr, fn in (('__NR_newfstatat', 'ksu_hook_newfstatat'), ('__NR_faccessat', 'ksu_hook_faccessat')):
    block = ("    err = ksu_register_syscall_hook(%s, %s);\n"
             "    if (err)\n"
             "        ret = err;\n") % (nr, fn)
    if block in s:
        s = s.replace(block, "    /* 5.4: %s 钩子暂时禁用 */\n" % fn, 1)
        ok.append(fn)
    else:
        print('[warn] 未匹配:', fn)

wr(p, s)
print('[ksu-diag3] 完成:', ', '.join(ok) if ok else '无改动')
