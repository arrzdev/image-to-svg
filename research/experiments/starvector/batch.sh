#!/bin/bash
# Sweep the repo's test inputs to map where StarVector's domain ends.
# Sequential on purpose -- one MPS device, parallel runs just contend.
cd "$(dirname "$0")" || exit 1
mkdir -p out
for name in "$@"; do
  for ext in png jpg; do
    src="../../../data/inputs/${name}.${ext}"
    [ -f "$src" ] && break
  done
  [ -f "$src" ] || { echo "SKIP  $name (not found)"; continue; }
  t0=$(date +%s)
  ./venv/bin/python -u starvector_mps.py "$src" -o "out/${name}.svg" \
      > "out/${name}.log" 2>&1
  rc=$?
  dt=$(( $(date +%s) - t0 ))
  tok=$(grep -o 'stream done: [0-9]*' "out/${name}.log" | tail -1 | grep -o '[0-9]*')
  if [ $rc -eq 0 ]; then
    stats=$(grep -o 'wrote .*' "out/${name}.log" | tail -1)
    echo "OK    ${name}  ${dt}s  ${tok:-?} tok  ${stats#wrote }"
  else
    echo "FAIL  ${name}  ${dt}s  ${tok:-?} tok  (see out/${name}.log)"
  fi
done
echo "BATCH COMPLETE"
