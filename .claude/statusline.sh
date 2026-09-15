#!/bin/bash
# Claude Code status line — project name, context, tokens, weekly sessions/compactions.
#
# Shipped by the cat-herder template and wired via .claude/settings.json ("statusLine").
# Reads the status JSON on stdin (context window, workspace dir) and prints a single line:
#
#   <project> | Ctx:<pct>% | Tok:<n> | Wk:<n> | Win:<sessions> Cmp:<compactions>
#
# The project name (first field) is the basename of the workspace/project dir, so every
# terminal running Claude Code shows which project it is — CC's auto tab-title is not
# configurable, so this status line is the reliable persistent project indicator.
#
# Weekly counters persist in $HOME/.claude/.weekly_state (reset Sunday 10am America/LA).

input=$(cat)

pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0' 2>/dev/null | cut -d. -f1)
in_tok=$(echo "$input" | jq -r '.context_window.total_input_tokens // 0' 2>/dev/null)
out_tok=$(echo "$input" | jq -r '.context_window.total_output_tokens // 0' 2>/dev/null)

# Project name (first field): basename of the project/workspace dir.
proj=$(echo "$input" | jq -r '.workspace.project_dir // .workspace.current_dir // .cwd // empty' 2>/dev/null)
proj=$(basename "$proj" 2>/dev/null)
if [ -n "$proj" ] && [ "$proj" != "." ] && [ "$proj" != "/" ]; then
  proj_prefix="$proj | "
else
  proj_prefix=""
fi

# Token formatting (K/M)
fmt_tok() {
  local t=$1
  if [ "$t" -ge 1000000 ] 2>/dev/null; then
    echo "$((t / 1000000)).$((t % 1000000 / 100000))M"
  elif [ "$t" -ge 1000 ] 2>/dev/null; then
    echo "$((t / 1000))K"
  else
    echo "$t"
  fi
}

total_tok=$((in_tok + out_tok))
tok_str=$(fmt_tok "$total_tok")

# --- Weekly reset key (Sunday 10am PST) ---
now_epoch=$(date +%s)
sun_10am=$(TZ=America/Los_Angeles date -j -f "%Y%m%d%H%M" \
  "$(TZ=America/Los_Angeles date -v-sun -v10H -v0M -v0S +%Y%m%d%H%M)" +%s 2>/dev/null)
if [ "$sun_10am" -gt "$now_epoch" ] 2>/dev/null; then
  sun_10am=$((sun_10am - 604800))
fi
WEEK_KEY="${sun_10am:-0}"

# --- State file: weekly tokens, sessions, compactions ---
STATE_FILE="$HOME/.claude/.weekly_state"

# Defaults
wk_tok=0; wk_sessions=0; wk_compactions=0; last_pct=0; last_tok=0

# Read state
if [ -f "$STATE_FILE" ]; then
  stored_week=$(sed -n '1p' "$STATE_FILE" 2>/dev/null)
  if [ "$stored_week" = "$WEEK_KEY" ]; then
    wk_tok=$(sed -n '2p' "$STATE_FILE" 2>/dev/null)
    wk_sessions=$(sed -n '3p' "$STATE_FILE" 2>/dev/null)
    wk_compactions=$(sed -n '4p' "$STATE_FILE" 2>/dev/null)
    last_pct=$(sed -n '5p' "$STATE_FILE" 2>/dev/null)
    last_tok=$(sed -n '6p' "$STATE_FILE" 2>/dev/null)
  fi
  # else: new week, defaults are 0
fi

# Detect new session: total tokens dropped to near zero (fresh context window)
if [ "$total_tok" -lt 50000 ] && [ "$last_tok" -gt 100000 ] 2>/dev/null; then
  wk_sessions=$((wk_sessions + 1))
fi

# Detect compaction: context % dropped significantly but tokens still high
# (not a fresh session — compaction shrinks context but tokens stay substantial)
pct_num=${pct:-0}
last_pct_num=${last_pct:-0}
drop=$((last_pct_num - pct_num))
if [ "$drop" -gt 15 ] && [ "$total_tok" -gt 100000 ] 2>/dev/null; then
  wk_compactions=$((wk_compactions + 1))
fi

# Accumulate tokens
wk_tok_new=$((wk_tok > total_tok ? wk_tok : wk_tok + total_tok))

# Write state
printf '%s\n%s\n%s\n%s\n%s\n%s\n' \
  "$WEEK_KEY" "$wk_tok_new" "$wk_sessions" "$wk_compactions" "$pct_num" "$total_tok" \
  > "$STATE_FILE" 2>/dev/null

weekly_str=$(fmt_tok "$wk_tok_new")

# --- Token burn rate warning ---
# High session tokens = context bloat risk, likely heading toward compaction
tok_warn=""
if [ "$total_tok" -ge 800000 ] 2>/dev/null; then
  tok_warn=" !! BURN"
elif [ "$total_tok" -ge 500000 ] 2>/dev/null; then
  tok_warn=" ! BURN"
fi

stats="Wk:$weekly_str | Win:$wk_sessions Cmp:$wk_compactions"

# --- Output ---
if [ -z "$pct" ] || [ "$pct" = "0" ] || [ "$pct" = "null" ]; then
  echo "${proj_prefix}Ctx:-- | Tok:$tok_str$tok_warn | $stats"
  exit 0
fi

if [ "$pct_num" -ge 85 ]; then
  echo "${proj_prefix}!! CTX ${pct}% HANDOFF !! | Tok:$tok_str$tok_warn | $stats"
elif [ "$pct_num" -ge 70 ]; then
  echo "${proj_prefix}! Ctx:${pct}% save | Tok:$tok_str$tok_warn | $stats"
else
  echo "${proj_prefix}Ctx:${pct}% | Tok:$tok_str$tok_warn | $stats"
fi
