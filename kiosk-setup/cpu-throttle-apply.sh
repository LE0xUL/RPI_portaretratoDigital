#!/usr/bin/env bash
# Aplica o revierte un límite de frecuencia de CPU para bajar consumo fuera del
# horario activo. Pensado para correr vía sudo (ver la regla en install.sh)
# desde screen-schedule.sh — no lo corras a mano salvo para debug.
#
# "low":    gobernador powersave + tope de frecuencia al mínimo del hardware.
# "normal": restaura el gobernador que estaba antes de "low" y el tope máximo
#           real del hardware.
set -u

MODE="${1:-}"
STATE_FILE="/run/photoframe-cpu-governor.orig"

case "$MODE" in
  low)
    : > "$STATE_FILE"
    for cpu in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
      [ -f "$cpu/scaling_governor" ] || continue
      current="$(cat "$cpu/scaling_governor" 2>/dev/null || echo "")"
      echo "$cpu $current" >> "$STATE_FILE"
      echo "powersave" > "$cpu/scaling_governor" 2>/dev/null || true
      if [ -f "$cpu/cpuinfo_min_freq" ]; then
        cat "$cpu/cpuinfo_min_freq" > "$cpu/scaling_max_freq" 2>/dev/null || true
      fi
    done
    ;;
  normal)
    for cpu in /sys/devices/system/cpu/cpu[0-9]*/cpufreq; do
      [ -f "$cpu/cpuinfo_max_freq" ] || continue
      cat "$cpu/cpuinfo_max_freq" > "$cpu/scaling_max_freq" 2>/dev/null || true
    done
    if [ -f "$STATE_FILE" ]; then
      while read -r cpu_path governor; do
        [ -n "$governor" ] && [ -f "$cpu_path/scaling_governor" ] && \
          echo "$governor" > "$cpu_path/scaling_governor" 2>/dev/null || true
      done < "$STATE_FILE"
      rm -f "$STATE_FILE"
    fi
    ;;
  *)
    echo "uso: $0 low|normal" >&2
    exit 1
    ;;
esac
