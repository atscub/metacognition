#!/usr/bin/env bash
# Find "not X, but Y" and similar negation patterns in text files.
# Usage: ./scripts/find-negation-patterns.sh [file or directory]
# Defaults to *.md files in current directory (recursive).

set -euo pipefail

target="${1:-.}"

if [[ -d "$target" ]]; then
  files=$(find "$target" -name '*.md' -not -path '*/node_modules/*' -not -path '*/.git/*')
else
  files="$target"
fi

# Colors
RED='\033[0;31m'
CYAN='\033[0;36m'
RESET='\033[0m'

patterns=(
  # "not X, but Y" / "not X — Y" / "not X; Y"
  'is not [^.;]*[,;—–] (it is|but|rather)'
  'are not [^.;]*[,;—–] (they are|but|rather)'
  'does not [^.;]*[,;—–] (it|but|rather)'
  'do not [^.;]*[,;—–] (they|but|rather)'
  'was not [^.;]*[,;—–] (it was|but|rather)'

  # "not X, it is Y" / "not X — it is Y"
  'not [^.;]*— it (is|was|does|requires|demands)'
  'not [^.;]*; it (is|was|does|requires|demands)'

  # "is not X. It is Y." (across sentence boundary)
  'is not [^.]*\. It is'
  'are not [^.]*\. They are'

  # Double negatives: "does not X without Y" / "cannot X without Y"
  'does not [^.;]* without'
  'do not [^.;]* without'
  'cannot [^.;]* without'

  # "not X but Y" (no comma)
  '\bnot [a-z]+ but [a-z]+'

  # "X, not Y" at end of clause (the reverse form)
  '[a-z]+, not [a-z ]+[.;]'

  # "is not a X — it is a Y"
  'is not (a|an) [^.;]*— (it is|this is)'
)

found=0

for file in $files; do
  [[ -f "$file" ]] || continue
  for pattern in "${patterns[@]}"; do
    matches=$(grep -niP "$pattern" "$file" 2>/dev/null || true)
    if [[ -n "$matches" ]]; then
      while IFS= read -r line; do
        found=1
        lineno=$(echo "$line" | cut -d: -f1)
        content=$(echo "$line" | cut -d: -f2-)
        printf "${CYAN}%s:%s${RESET} %s\n" "$file" "$lineno" "$content"
      done <<< "$matches"
    fi
  done
done

if [[ $found -eq 0 ]]; then
  echo "No negation patterns found."
fi
