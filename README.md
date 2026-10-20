# ufw_prune.py

Safely bulk-delete ufw rules using **original rule numbers** from a single snapshot — no re-checking indexes between deletions.

## Why

`ufw delete <n>` renumbers the list after every deletion. Deleting rule 5 then rule 8 means rule 8 is now 7 — and you nuke the wrong rule. This script snapshots `ufw status numbered` once, then deletes your selection in a safe, remapped order.

## Install

```bash
chmod +x ufw_prune.py
# run with sudo (ufw requires it)
```

Requires Python 3.6+. No dependencies.

## Usage

```bash
# Interactive: shows the rule list, prompts for numbers
sudo python3 ufw_prune.py

# Preview without changing anything
sudo python3 ufw_prune.py --dry-run 5 8-12

# Delete by original numbers / ranges
sudo python3 ufw_prune.py 5 8 12
sudo python3 ufw_prune.py 5-12

# Wipe everything
sudo python3 ufw_prune.py --all
```

## How it stays safe

1. **Snapshot once** — original numbers never shift from your perspective.
2. **Deletes descending** — lower indexes can't be invalidated mid-run.
3. **Spec-based deletion first** — tries `ufw delete allow from X to any port Y`, which is order-independent.
4. **Text-matching fallback** — if spec parsing fails, re-queries current state and matches the snapshot's exact rule text.
5. **Fails safe** — a rule it can't confidently delete is reported as `FAILED` for manual removal, never guessed at.

## Recommended workflow

```bash
# 1. Backup before touching anything
sudo ufw show added > ~/ufw_backup_$(date +%F).rules

# 2. Preview
sudo python3 ufw_prune.py --dry-run

# 3. Execute
sudo python3 ufw_prune.py <numbers/ranges>

# 4. Verify
sudo ufw status numbered
```

## Notes

- Rules with unusual syntax are handled, but anything unparseable is flagged for manual deletion rather than risk-deleted.
- Deleting by spec removes both IPv4 and IPv6 variants where ufw manages them together.
- Run as root: `sudo python3 ufw_prune.py ...`
