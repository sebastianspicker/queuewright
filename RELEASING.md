# Release procedure

Queuewright has no published release or package artifact. A source prerelease
must be built from one reviewed commit.

1. Confirm the version in `studio-ui/package.json`,
   `studio-ui/package-lock.json`, `CHANGELOG.md`, and the release notes.
2. Review the complete file manifest and ignored-file boundary.
3. Review all publishable configuration files for credentials and private
   data.
4. Review Python and npm dependency versions and licenses.
5. Complete `RELEASE_CHECKLIST.md`.
6. Create the candidate commit.
7. Run every gate again from that exact commit.
8. Push the reviewed branch.
9. Create tag `v0.1.0-alpha.1`.
10. Publish a GitHub prerelease using
    `docs/releases/0.1.0-alpha.1.md`.

Restart verification if any check changes the working tree. Do not publish when
clean installation, tests, browser checks, screenshots, security review, or
dependency review remain incomplete.
