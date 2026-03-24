#!/usr/bin/env bash

###################################################################
# NOTES
# Reports PRs that have been merged to main over the last N days
# expects --days N argument and the github org/reponame
# Example:  github_pr_reports.sh -d 7 orgname/reponame

set -euo pipefail
IFS=$'\n\t'

usage() {
  cat <<EOF
Usage: $0 [--days N] <owner/repo>

Options:
  -d, --days N   Number of days to look back (default: 7)
  -h, --help     Show this help message
EOF
  exit 1
}

# parse args
DAYS=7
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case $1 in
    -d|--days)
      shift
      [[ -z ${1-} || $1 == -* ]] && { echo "Error: --days requires a number"; usage; }
      DAYS=$1
      ;;
    -h|--help) usage ;;
    --) shift; break ;;
    -*)
      echo "Error: Unknown option: $1"
      usage
      ;;
    *)
      POSITIONAL+=("$1")
      ;;
  esac
  shift
done

if [[ ${#POSITIONAL[@]} -ne 1 ]]; then
  echo "Error: You must supply exactly one repo (owner/name)"
  usage
fi
REPO=${POSITIONAL[0]}

# figure out “since” date
if command -v gdate &>/dev/null; then
  # GNU date (MacOS with coreutils)
  SINCE=$(gdate -d "${DAYS} days ago" '+%Y-%m-%d')
else
  # Standard Linux date command
  SINCE=$(date -d "${DAYS} days ago" '+%Y-%m-%d')
fi

# fetch list of merged PRs 
PR_JSON=$(gh pr list \
  --repo "$REPO" \
  --state merged \
  --base main \
  --search "merged:>=${SINCE}" \
  --json number,title,mergedAt,additions,deletions)

# print header
echo "## Weekly “main” Merge Report for $REPO"
echo
echo "- **Since:** $SINCE"
echo "- **Total PRs merged:** $(echo "$PR_JSON" | jq '. | length')"
echo
echo "### Details:"
echo

# iterate each PR and then list its files
echo "$PR_JSON" | jq -c '.[]' | while read -r pr; do
  number=$(echo "$pr" | jq '.number')
  title=$(echo "$pr" | jq -r '.title')
  mergedAt=$(echo "$pr" | jq -r '.mergedAt')
  additions=$(echo "$pr" | jq '.additions')
  deletions=$(echo "$pr" | jq '.deletions')

  # PR summary line
  echo "- [#$number](https://github.com/$REPO/pull/$number) "$title" — merged $mergedAt (+$additions − $deletions)"

  # now fetch files for that PR
  echo "  - **Files changed:**"
  gh pr view "$number" \
    --repo "$REPO" \
    --json files \
  | jq -r '
      .files[] 
      | "    - \(.path) (+\(.additions) − \(.deletions))"
    '
  
  # blank line between PRs
  echo  
done
