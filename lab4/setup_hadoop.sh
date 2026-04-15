#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/malikmuhametzanov/PycharmProjects/burn/lab4"
HADOOP_HOME="$ROOT/tools/hadoop-3.4.2"

export JAVA_HOME="/Library/Java/JavaVirtualMachines/temurin-21.jdk/Contents/Home"
export HADOOP_HOME
export HADOOP_CONF_DIR="$HADOOP_HOME/etc/hadoop"
export HADOOP_LOG_DIR="$HADOOP_HOME/logs"
export HADOOP_PID_DIR="$ROOT/hadoop-pids"
export HADOOP_NICENESS=0
export PATH="$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH"

mkdir -p "$ROOT/hadoop-data/name" "$ROOT/hadoop-data/data" "$ROOT/hadoop-data/tmp" "$HADOOP_LOG_DIR" "$HADOOP_PID_DIR"

if [ ! -f "$ROOT/hadoop-data/name/current/VERSION" ]; then
  "$HADOOP_HOME/bin/hdfs" namenode -format -force -nonInteractive
fi

echo "Hadoop prepared at $HADOOP_HOME"
