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

"$ROOT/setup_hadoop.sh"
"$HADOOP_HOME/bin/hdfs" --daemon start namenode
"$HADOOP_HOME/bin/hdfs" --daemon start datanode
"$HADOOP_HOME/bin/hdfs" dfsadmin -report


"$HADOOP_HOME/bin/hdfs" dfs -mkdir -p /user/student/patents
"$HADOOP_HOME/bin/hdfs" dfs -put -f /Users/malikmuhametzanov/PycharmProjects/burn/lab4/outputs/data/variant_1_patents.json /user/student/patents/variant_1_patents.json
"$HADOOP_HOME/bin/hdfs" dfs -ls /user/student/patents
"$HADOOP_HOME/bin/hdfs" dfs -cat /user/student/patents/variant_1_patents.json | head
