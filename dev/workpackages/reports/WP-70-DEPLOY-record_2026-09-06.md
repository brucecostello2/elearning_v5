# WP-70 deploy record -- node-01, api + frontend, 2026-09-06

- Built from main 9c406e8a30cd15fab4764596e1324422385c4878, tag v5.42.0-wp70, repo-root context, api built with IVGS_BUILD_REF/IVGS_BUILD_SHA.
- ivgs-infra/.env (gitignored, WP-34 rule 7): IVGS_API_TAG v5.41.3-rct-parent-repair -> v5.42.0-wp70; IVGS_FRONTEND_TAG v5.41.0-rct-exits -> v5.42.0-wp70.
- Banked: /mnt/ivgs-shared/image-artifacts/brucecostello2_ivgs-api_v5.42.0-wp70.tar.zst (sha256 e16b1cb8...) and ..._ivgs-frontend_v5.42.0-wp70.tar.zst (sha256 6818110d...); sidecar digests equal the built image ids. Not pushed to GHCR (off the deploy path, CLAUDE.md 6.1).
- Recreated with the label-derived invocation (two -f files, --env-file, --force-recreate --no-deps --pull never): fastapi-backend then nextjs-frontend; both healthy in 9 s.
- ivgs-fastapi -> ghcr.io/brucecostello2/ivgs-api:v5.42.0-wp70 sha256:30dc415da3a64fe398f0f2e9cdaa2e04292ca87604af411b8d9bac15e4ee5600; GET /api/v1/health 200 version v5.42.0-wp70; /api/v1/version commit_sha 9c406e8.
- ivgs-nextjs -> ghcr.io/brucecostello2/ivgs-frontend:v5.42.0-wp70 sha256:1f85f6a9d6dbb3688b4c25edaeb72fd5e0ddc5a507a184f784b78c9b1c7f9d24.
- Rollback: restore the two previous tags in ivgs-infra/.env and recreate the same two services with the same invocation; both previous images remain in the local store and the artifact store.
