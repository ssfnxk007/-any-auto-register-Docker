#!/bin/bash
set -e

APP_PORT="${PORT:-8000}"
ENABLE_NOVNC="${ENABLE_NOVNC:-false}"

# 清理可能残留的 Xvfb 锁文件
rm -f /tmp/.X11-unix/X99 /tmp/.X99-lock

# 启动虚拟显示
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
export DISPLAY=:99

# 等待 Xvfb 就绪
sleep 1

if [ "$ENABLE_NOVNC" = "true" ]; then
    # 启动 x11vnc（无密码，仅本地 VNC）
    if [ -n "$VNC_PASSWORD" ]; then
        x11vnc -display :99 -rfbauth <(x11vnc -storepasswd "$VNC_PASSWORD" /tmp/vncpass && echo /tmp/vncpass) -forever -shared &
    else
        x11vnc -display :99 -nopw -forever -shared &
    fi

    # 启动 noVNC（端口 6080 -> VNC 5900）
    websockify --web=/usr/share/novnc 6080 localhost:5900 &
fi

if [ "$RELOAD" = "true" ]; then
    RELOAD_ARGS="--reload"
else
    RELOAD_ARGS=""
fi

# 启动 FastAPI 后端
exec uvicorn main:app --host 0.0.0.0 --port "$APP_PORT" $RELOAD_ARGS
