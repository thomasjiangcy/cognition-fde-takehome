# Managed playbooks

Store Devin playbook bodies in this directory as `*.devin.md` files. Declare
each file's path, title, and unique macro beside the workflow that owns it, then
include the declaration in the startup resource registry.

Application startup reconciles registered files with organization playbooks in
Devin. It creates missing playbooks, updates changed playbooks, and leaves
already-matching playbooks unchanged.
