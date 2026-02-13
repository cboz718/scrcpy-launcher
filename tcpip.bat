@echo off
scrcpy.exe --tcpip --show-touches --stay-awake --pause-on-exit=if-error %*
