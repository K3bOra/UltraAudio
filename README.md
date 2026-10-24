# UltraAudio — Official update repository

Official repository: **K3bOra/UltraAudio**. Enigma2 plugin for **Python 3.5+** images.

**Status: repository setup only. No plugin package or release has been uploaded or published.**

## Update address

The prepared updater will read `https://github.com/K3bOra/UltraAudio/releases/latest/download/update.json`. This address will become available only after the final version is approved and the first release is published. The plugin will be configured with `K3bOra/UltraAudio`, so users do not need to type the source manually.

The manifest contains the tag-specific IPK URL, SHA-256, byte size, version, and Arabic/English release notes. The receiver verifies the downloaded package identity, version, size, and hash before running OPKG.

## Publish later, after explicit approval

1. Finish and test the plugin on the receiver.
2. After final approval, place exactly one current IPK in `packages/`. Its filename and internal package version must match.
3. Fill in `release-notes.json` with the changes in English and Arabic.
4. Commit the changes to `main`. This does **not** publish a release.
5. Only when publication is requested, run **Actions → Publish verified UltraAudio release → Run workflow**.

The workflow has **only a manual trigger**. Commits and tags do not run it. It rejects missing or multiple IPKs, validates Python syntax and package contents, and generates metadata from the actual package. It uploads a draft, downloads and checks both assets, then publishes the release. It refuses to overwrite an existing release. No credentials are embedded in the plugin.

A root `update.json` bootstrap file for older clients will be created only after the first release is published. There is no dummy or placeholder update manifest.

## Local validation when a package is available

Run `python3 scripts/prepare_release.py`. It intentionally stops if no approved IPK is present. Generated `dist/` and `verified/` files are not committed.
