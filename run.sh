#!/bin/sh
# 构建并启动 Disc Image Studio Linux 图形前端。
set -e
cd "$(dirname "$0")"
go build -trimpath -o dis-gui .
exec ./dis-gui "$@"
