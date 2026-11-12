/* MIT: small ARM Linux constructor; fork, close inherited fds, exec shell. */
.syntax unified
.thumb
.arch armv7-a
.text
.global launch
launch:
 push {r4,r5,lr}
 movs r7,#2
 svc #0
 cmp r0,#0
 blt done
 bne done
 movs r5,#3
1:
 movs r7,#6
 mov r0,r5
 svc #0
 adds r5,#1
 cmp.w r5,#256
 blo 1b
 movs r7,#5
 adr r0,output
 movw r1,#0x241
 movw r2,#0x1a4
 svc #0
 mov r4,r0
 cmp r4,#0
 blt execute
 movs r7,#63
 mov r0,r4
 movs r1,#1
 svc #0
 movs r7,#63
 mov r0,r4
 movs r1,#2
 svc #0
 movs r7,#6
 mov r0,r4
 svc #0
execute:
 sub sp,#32
 adr r0,shell
 str r0,[sp]
 adr r0,script
 str r0,[sp,#4]
 movs r0,#0
 str r0,[sp,#8]
 adr r0,environment
 str r0,[sp,#16]
 movs r0,#0
 str r0,[sp,#20]
 movs r7,#11
 adr r0,shell
 mov r1,sp
 add r2,sp,#16
 svc #0
 movs r7,#1
 movs r0,#127
 svc #0
done:
 pop {r4,r5,pc}
 .hword 0x46c0
shell: .asciz "/bin/sh"
script: .asciz "/tmp/jiritsu/run.sh"
output: .asciz "/tmp/jiritsu/out.txt"
 .balign 2,0
 .hword 0x46c0
environment: .asciz "PATH=/bin:/sbin:/usr/bin:/usr/sbin"
 .balign 4,0
