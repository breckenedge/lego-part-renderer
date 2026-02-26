# Project Notes

## Environment

- Docker Desktop is available via WSL2 but may need to be started manually before use
- The render service starts in a few seconds, don't wait long for it

## Development

- Always begin feature and debugging development by writing a test first
- Tests in this project use golden renders — if you change them, ask a human to review the output

## Versioning

- Auto-versioning is handled by `.github/workflows/release.yml`
- On every successful build on main, the patch version is bumped automatically (e.g. v0.0.1 -> v0.0.2)
- The release workflow creates a tag which triggers the build workflow to publish a Docker image and GitHub Release
- CHANGELOG.md is updated automatically by the release workflow — do not edit it manually
- To bump major or minor version, manually create a tag (e.g. `git tag v1.0.0 && git push --tags`) — subsequent auto-releases will increment the patch from there
