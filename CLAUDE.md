# Project Notes

## Versioning

- Uses semver git tags (e.g. `v1.0.0`)
- Pushing a `v*` tag triggers the CI workflow which builds/publishes the Docker image and creates a GitHub Release with auto-generated notes
- Docker image tags match the semver tag (e.g. `ghcr.io/breckenedge/lego-part-renderer:1.0.0`)
- `latest` tag is updated on every push to `main`

### Release process

```bash
git tag v1.0.0
git push origin v1.0.0
```

CI handles the rest: Docker build, publish to ghcr.io, and GitHub Release creation.

## Environment

- Docker Desktop is available via WSL2 but may need to be started manually before use
