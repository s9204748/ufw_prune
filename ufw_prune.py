#!/usr/bin/env python3
"""
ufw_prune.py - Safely delete ufw rules by their ORIGINAL numbered-status indexes.

Snapshots `ufw status numbered` once, then deletes selected rules descending,
remapping indexes internally so you never re-check numbering between deletions.

Usage:
  sudo python3 ufw_prune.py                      # interactive: shows list, asks for numbers
  sudo python3 ufw_prune.py 5 8 12               # delete original-numbered 5, 8, 12
  sudo python3 ufw_prune.py 5-12                 # delete original-numbered 5 through 12
  sudo python3 ufw_prune.py --all                # delete every rule (full wipe)
  sudo python3 ufw_prune.py --dry-run 5 8-12     # show what WOULD be deleted, change nothing
"""

import subprocess
import re
import sys

SNAPSHOT_HEADER = "=== ufw rules (original snapshot) ==="


def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)


def snapshot_rules():
    """Parse `ufw status numbered` into {orig_num: rule_string}."""
    out = run("sudo ufw status numbered").stdout
    rules = {}
    for line in out.splitlines():
        m = re.match(r"\[\s*(\d+)\]\s+(.+)", line)
        if m:
            rules[int(m.group(1))] = m.group(2).strip()
    return rules


def show(rules):
    print(SNAPSHOT_HEADER)
    for n in sorted(rules):
        print(f"  [{n:>3}]  {rules[n]}")
    print()


def parse_selections(tokens):
    """Turn '5 8-12' style args into a set of original numbers."""
    nums = set()
    for tok in tokens:
        if "-" in tok:
            a, b = tok.split("-", 1)
            nums.update(range(int(a), int(b) + 1))
        else:
            nums.add(int(tok))
    return nums


def delete_rule(orig_num, rule_text):
    """Delete a rule by its full spec (order-independent, immune to renumbering)."""
    # Strip the v6 duplicate marker / brackets, keep the rule body
    spec = rule_text
    # ufw accepts deleting by spec like: ufw delete allow from X to any port Y
    # The status output is already in that form, e.g.:
    #   "4444/tcp ALLOW IN  10.48.133.63"  ->  delete allow from 10.48.133.63 to any port 4444 proto tcp
    #   "Anywhere ALLOW IN  192.168.1.0/24" -> delete allow from 192.168.1.0/24
    #   "Anywhere on tun0 ALLOW IN Anywhere" -> delete allow in on tun0
    #   "8083/tcp ALLOW OUT Anywhere"        -> delete allow out ... (out rules: no 'from' clause needed)

    m = re.match(r"^(?P<ports>\S+)\s+ALLOW\s+(?P<dir>IN|OUT)\s+(?P<src>\S+)(?:/(?P<proto>tcp|udp))?", spec)
    if not m:
        return None  # complex rule; caller falls back to numbered delete

    ports, direction, src = m.group("ports"), m.group("dir").lower(), m.group("src")
    proto = m.group("proto")
    port_any = ports == "Anywhere"
    src_any = src == "Anywhere" or src.endswith("/tcp") or src.endswith("/udp")

    cmd = f"sudo ufw delete allow {direction}"
    if not src_any:
        cmd += f" from {src.rsplit('/', 1)[0] if '/' in src and proto else src}"
    if not port_any:
        plist = ports.split(",")
        cmd += " to any port " + plist[0]
        if len(plist) > 1:
            cmd += f" ports {','.join(plist)}"
        cmd += f" proto {proto}" if proto else ""
    out = run(cmd)
    return out.returncode == 0


def delete_numbered(orig_num, rules_snapshot):
    """Fallback: delete by CURRENT position, computed from how many were already removed."""
    # Rules with orig number < current candidate have shifted: current index = orig - removed_below
    # We compute this by re-querying state instead of bookkeeping: safer.
    out = run("sudo ufw status numbered").stdout
    current = {}
    for line in out.splitlines():
        m = re.match(r"\[\s*(\d+)\]\s+(.+)", line)
        if m:
            current[int(m.group(1))] = m.group(2).strip()
    # find the current rule whose text matches the original snapshot entry
    target = rules_snapshot[orig_num]
    for n, text in current.items():
        if text == target:
            out = run(f"sudo ufw --force delete {n}")
            return out.returncode == 0
    return False  # already gone


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    wipe = "--all" in args
    tokens = [a for a in args if not a.startswith("--")]

    rules = snapshot_rules()
    if not rules:
        print("No rules found (or ufw inactive). Nothing to do.")
        sys.exit(0)

    show(rules)

    if wipe:
        targets = set(rules)
    elif tokens:
        targets = parse_selections(tokens)
    else:
        # interactive
        sel = input("Enter original numbers/ranges to delete (e.g. 5 8-12 30), or 'all': ").strip()
        if sel.lower() == "all":
            targets = set(rules)
        else:
            targets = parse_selections(sel.split())

    invalid = targets - set(rules)
    if invalid:
        print(f"[!] Not in snapshot (ignored): {sorted(invalid)}")
    targets &= set(rules)
    if not targets:
        print("Nothing selected.")
        sys.exit(0)

    mode = "WOULD DELETE (dry run)" if dry_run else "DELETING"
    print(f"--- {mode}: {len(targets)} rule(s), descending ---")
    ok, fail = 0, 0

    for n in sorted(targets, reverse=True):
        text = rules[n]
        print(f"  [{n:>3}] {text} ... ", end="", flush=True)
        if dry_run:
            print("ok (dry)")
            continue
        # Try spec-based delete first (immune to renumbering); fall back to remapped numbered delete
        if delete_rule(n, text) or delete_numbered(n, rules):
            print("ok")
            ok += 1
        else:
            print("FAILED (may already be gone, or complex rule - delete manually)")
            fail += 1

    if not dry_run:
        print(f"\n[+] Deleted: {ok}  Failed: {fail}")
        after = run("sudo ufw status numbered").stdout
        print("\n=== post-delete status ===")
        print(after)


if __name__ == "__main__":
    main()
