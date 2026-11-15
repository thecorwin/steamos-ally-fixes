# Tag-stripping copy for the patched sapi.dll (see patch_sapi_setinterest.py).
# Replaces the memcpy in spvoice_Speak's plain-text path:
#   in:  rcx = destination (UTF-16), rdx = source (UTF-16, NUL-terminated)
#   out: rax = destination, r13 = characters written (without the NUL)
# Copies the text, leaving out everything from '<' to the next '>'. A '>' outside a tag is kept.
# Leaf function: no stack use, touches only rax, rdx, r8, r9, r10, r13.
        .intel_syntax noprefix
        .text
        .globl strip_tags
strip_tags:
        mov     rax, rcx
        mov     r9, rcx
        xor     r10d, r10d              # 1 while inside <...>
1:      movzx   r8d, word ptr [rdx]
        add     rdx, 2
        test    r8d, r8d
        jz      4f
        cmp     r8d, 0x3c               # '<'
        je      2f
        test    r10d, r10d
        jnz     3f
        mov     word ptr [r9], r8w
        add     r9, 2
        jmp     1b
2:      mov     r10d, 1
        jmp     1b
3:      cmp     r8d, 0x3e               # '>' closes the tag
        jne     1b
        xor     r10d, r10d
        jmp     1b
4:      mov     word ptr [r9], 0
        mov     r13, r9
        sub     r13, rax
        shr     r13, 1
        ret
