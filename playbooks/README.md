# Managed playbooks

Store Devin playbook bodies in this directory as `*.devin.md` files. Register
each file's path, title, and unique macro in `app/devin/playbooks.py`.

Application startup reconciles registered files with organization playbooks in
Devin. It creates missing playbooks, updates changed playbooks, and leaves
already-matching playbooks unchanged. This directory intentionally contains no
playbook definitions yet.
