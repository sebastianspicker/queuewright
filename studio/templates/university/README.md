# University starter

This directory contains the default fictional Studio starter:

- `profile.json`;
- `university.desired-state.json`.

Current validation reports 11 groups, seven ticket-bearing services, seven
roles, three organizations, seven synthetic staff accounts, three synthetic
customer accounts, and eight internal test scenarios.

The starter also covers the 14 feature families materialized by the V1
compiler and records decisions for the 19-family capability registry.

## Customize

Replace:

- profile and manifest identifiers;
- display name, managed prefix, and technical namespace;
- service tree and service codes;
- organizations, roles, and access;
- fictional population names;
- field labels and options;
- schedules, report scope, handoff rules, and service ownership;
- internal test scenarios.

Keep these safety settings:

- `offline_only=true`;
- fictional `example.invalid` identities;
- existing-object writes and deletion disabled;
- organizations unshared and domain assignment disabled;
- notifications and external effects disabled;
- checklists inactive;
- automation fenced to managed resources;
- internal test data retained locally.

## Validate

Run from the repository root:

```bash
python3 -m queuewright validate \
  studio/templates/university/profile.json
python3 -m queuewright plan \
  studio/templates/university/profile.json
python3 -m queuewright self-test
```
