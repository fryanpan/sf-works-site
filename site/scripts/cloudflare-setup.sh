#!/usr/bin/env bash
# Set up the Cloudflare credentials this site deploys with, on a machine that
# has never had them.
#
#     scripts/cloudflare-setup.sh            # full setup, prompts where it must
#     scripts/cloudflare-setup.sh --check    # report what is already in place
#     scripts/cloudflare-setup.sh --github   # only push the two GitHub secrets
#
# The token is typed once, into a hidden prompt, and goes straight into the
# macOS keychain. It is never written to a file, never passed on a command line
# where `ps` would show it, and never echoed. Everything after that reads it
# back out of the keychain.
#
# What this script cannot do, and why: minting the token itself. That is done
# in Cloudflare's own dashboard, signed in as you. The script prints the exact
# page and the exact permissions and waits.

set -euo pipefail

SERVICE_TOKEN="sf-works-cloudflare-api-token"
SERVICE_ACCOUNT="sf-works-cloudflare-account-id"
ZONE="sf-works.org"
# The repo the deploy runs in. The site now lives in `site/` inside the private
# fryanpan/sf-works repo, which is where the workflow and therefore the secrets
# belong. Derived from the checkout's own remote so it cannot drift, and empty
# until the repo has one.
# `|| true` inside the substitution matters: with `set -e` and `pipefail`, a
# checkout with no remote makes git exit non-zero and takes the whole script
# with it, before a single line is printed.
_remote="$(git -C "$(dirname "$0")/.." remote get-url origin 2>/dev/null || true)"
REPO="${SF_WORKS_REPO:-$(printf '%s' "$_remote" \
  | sed -E 's#(git@github.com:|https://github.com/)##; s#\.git$##')}"
API="https://api.cloudflare.com/client/v4"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
warn() { printf '\033[33m%s\033[0m\n' "$*"; }
fail() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }

kc_get()  { security find-generic-password -s "$1" -w 2>/dev/null || true; }
kc_set()  { security add-generic-password -U -a "$USER" -s "$1" -w "$2" >/dev/null; }

# Every call to Cloudflare goes through here so the token reaches curl through
# a file descriptor rather than an argument. An argument is visible to every
# other process on the machine for as long as the call runs.
cf() {
  local path="$1"; shift
  local token; token="$(kc_get "$SERVICE_TOKEN")"
  [ -n "$token" ] || fail "No token in the keychain. Run this script with no arguments first."
  curl -sS --fail-with-body \
    -H @<(printf 'Authorization: Bearer %s\n' "$token") \
    -H "Content-Type: application/json" \
    "$API$path" "$@"
}

jqr() { python3 -c 'import json,sys;d=json.load(sys.stdin);print(eval(sys.argv[1],{"d":d}) if d else "")' "$1"; }

instructions() {
  cat <<'TXT'

Mint the token in the Cloudflare dashboard, signed in to the SF Works account.

  1. https://dash.cloudflare.com/profile/api-tokens
  2. "Create Token" -> "Edit Cloudflare Workers" -> "Use template"
  3. Set the scopes to the SF Works account and the sf-works.org zone:
       Account Resources : Include -> SF Works
       Zone Resources    : Include -> Specific zone -> sf-works.org
  4. The template already grants what a deploy needs:
       Account | Workers Scripts        | Edit
       Account | Account Settings       | Read
       Zone    | Workers Routes         | Edit
     Add one more, because the site claims its hostnames as Custom Domains and
     that writes DNS records:
       Zone    | DNS                    | Edit
  5. Continue to summary -> Create Token -> copy the value.

The value is shown once. Paste it at the prompt below; nothing echoes.

TXT
}

setup_token() {
  local existing; existing="$(kc_get "$SERVICE_TOKEN")"
  if [ -n "$existing" ]; then
    bold "A token is already in the keychain ($SERVICE_TOKEN)."
    read -r -p "Replace it? [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]] || return 0
  fi

  instructions
  local token
  read -r -s -p "Cloudflare API token: " token
  echo
  [ -n "$token" ] || fail "Nothing entered."

  kc_set "$SERVICE_TOKEN" "$token"
  unset token

  local status
  status="$(cf /user/tokens/verify | jqr 'd["result"]["status"]')"
  [ "$status" = "active" ] || fail "Cloudflare says the token is '$status', not active."
  bold "Token stored and verified active."
}

setup_account() {
  local body; body="$(cf /accounts)"
  local n; n="$(echo "$body" | jqr 'len(d["result"])')"
  [ "$n" != "0" ] || fail "The token can see no accounts. It is scoped to the wrong place."

  if [ "$n" = "1" ]; then
    local id name
    id="$(echo "$body" | jqr 'd["result"][0]["id"]')"
    name="$(echo "$body" | jqr 'd["result"][0]["name"]')"
    kc_set "$SERVICE_ACCOUNT" "$id"
    bold "Account: $name"
    echo "  id stored in the keychain as $SERVICE_ACCOUNT"
  else
    warn "The token can see $n accounts. It should see one — the SF Works account."
    echo "$body" | python3 -c 'import json,sys
for a in json.load(sys.stdin)["result"]: print(f"  {a[\"name\"]}  {a[\"id\"]}")'
    fail "Re-mint the token scoped to the SF Works account only, then run this again."
  fi
}

check_zone() {
  local body n
  body="$(cf "/zones?name=$ZONE")"
  n="$(echo "$body" | jqr 'len(d["result"])')"
  if [ "$n" = "0" ]; then
    warn "The token cannot see the zone $ZONE."
    echo "  Either the zone lives in a different Cloudflare account, or the token"
    echo "  was not scoped to it. If $ZONE is still registered under your personal"
    echo "  account, move it: dash.cloudflare.com -> the zone -> Overview ->"
    echo "  Advanced Actions -> Move to another account -> SF Works."
    echo "  A registrar transfer between your own accounts is free and keeps DNS."
    return 1
  fi
  local status; status="$(echo "$body" | jqr 'd["result"][0]["status"]')"
  bold "Zone $ZONE is visible to the token, status: $status"
  local recs; recs="$(cf "/zones/$(echo "$body" | jqr 'd["result"][0]["id"]')/dns_records" | jqr 'len(d["result"])')"
  echo "  $recs DNS record(s). The four staging hostnames and the apex are created"
  echo "  by wrangler on first deploy, because wrangler.toml claims them as custom"
  echo "  domains. Nothing to add by hand."
}

push_github() {
  local token id
  token="$(kc_get "$SERVICE_TOKEN")"
  id="$(kc_get "$SERVICE_ACCOUNT")"
  if [ -z "$token" ] || [ -z "$id" ]; then
    # Say WHY the read failed. On 2026-09-22 both items were present and readable
    # from another session on the same machine while this line reported them
    # missing, and the swallowed stderr was the only place the reason lived.
    warn "Keychain read failed for the token or the account id. security says:"
    security find-generic-password -s "$SERVICE_TOKEN"   >/dev/null 2>&1 || security find-generic-password -s "$SERVICE_TOKEN"   -w 2>&1 >/dev/null | sed 's/^/    /'
    security find-generic-password -s "$SERVICE_ACCOUNT" >/dev/null 2>&1 || security find-generic-password -s "$SERVICE_ACCOUNT" -w 2>&1 >/dev/null | sed 's/^/    /'
    echo "  If the items exist but this shell cannot read them, run this from Terminal.app"
    echo "  rather than from inside another program, and click Always Allow if macOS asks."
    fail "Nothing was pushed to GitHub."
  fi

  if [ -z "$REPO" ]; then
    warn "This checkout has no git remote, so there is no repo to set secrets on."
    echo "  The deploy workflow lives here, in .github/workflows/deploy.yml, and"
    echo "  runs on GitHub — so this repo has to exist on GitHub before a deploy"
    echo "  can happen. Creating it is Bryan's to do: the site repo is public and"
    echo "  agents do not create or flip public repos."
    echo "  Once it exists:  git remote add origin git@github.com:<owner>/<name>.git"
    echo "                   scripts/cloudflare-setup.sh --github"
    return 1
  fi

  if ! gh repo view "$REPO" >/dev/null 2>&1; then
    warn "The repo $REPO is not reachable."
    echo "  Create it first, then: scripts/cloudflare-setup.sh --github"
    echo "  (Override the name with SF_WORKS_REPO=owner/name.)"
    return 1
  fi

  # `gh secret set` reads the value from stdin when --body is absent. There is
  # no --body-file flag, and passing --body would put the token in the process
  # arguments where `ps` can read it.
  #
  # Each call is checked rather than left to `set -e`, because this function is
  # invoked as `push_github || true` and bash suppresses -e for the whole body
  # of a function called in an || list. That is why an earlier run printed
  # "Both secrets set" twice over two failed calls and then found no secrets.
  printf '%s' "$token" | gh secret set CLOUDFLARE_API_TOKEN  --repo "$REPO" \
    || fail "Could not set CLOUDFLARE_API_TOKEN on $REPO."
  printf '%s' "$id"    | gh secret set CLOUDFLARE_ACCOUNT_ID --repo "$REPO" \
    || fail "Could not set CLOUDFLARE_ACCOUNT_ID on $REPO."

  # Read them back. A set that reports success and stores nothing is the failure
  # this whole block exists to make impossible.
  local have
  have="$(gh secret list --repo "$REPO" --json name -q '.[].name' 2>/dev/null | sort | tr '\n' ' ')"
  case "$have" in
    *CLOUDFLARE_ACCOUNT_ID*CLOUDFLARE_API_TOKEN*)
      bold "Both secrets set on $REPO and read back." ;;
    *)
      fail "Set reported success but $REPO lists: ${have:-(nothing)}" ;;
  esac
}

report() {
  local t a
  t="$(kc_get "$SERVICE_TOKEN")"; a="$(kc_get "$SERVICE_ACCOUNT")"
  echo "keychain $SERVICE_TOKEN   : $([ -n "$t" ] && echo present || echo MISSING)"
  echo "keychain $SERVICE_ACCOUNT : ${a:-MISSING}"
  [ -n "$t" ] || return 0
  check_zone || true
  if [ -z "$REPO" ]; then
    echo "github secrets    : this checkout has no remote, so no repo to check"
  else
    gh secret list --repo "$REPO" 2>/dev/null || echo "github secrets    : $REPO not reachable"
  fi
}

case "${1:-}" in
  --check)  report ;;
  --github) push_github ;;
  "")       setup_token; setup_account; check_zone || true; push_github || true ;;
  *)        fail "Unknown argument: $1" ;;
esac
