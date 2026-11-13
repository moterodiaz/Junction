#!/usr/bin/env bash
# Throwaway pipeline smoke test. Never executed; will be reverted.
arr=(a b c)
for ((i=0; i<=${#arr[@]}; i++)); do
  echo "${arr[$i]}"
done
rm -rf $DIR/
