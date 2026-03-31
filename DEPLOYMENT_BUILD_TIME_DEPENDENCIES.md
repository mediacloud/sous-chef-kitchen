# Build-Time Dependency Strategy for Kitchen Deployments

## Why this is needed

Intermittent run startup failures indicate shared-runtime setup races:

- `apt-get` lock contention (`/var/lib/dpkg/lock-frontend`)
- transient filesystem/state errors during install (`setuptools*.dist-info` missing)
- missing cloned paths during concurrent pull/setup

These are consistent with multiple runs performing mutable environment setup at the same time.

## Current risk points

`docker/prefect.yaml.in` currently performs mutable setup during pull/startup:

- `run_shell_script` with `apt-get update && apt-get install ...`
- `pip install --upgrade pip setuptools wheel ...`
- `pip_install_requirements` from repo checkout

When multiple runs start close together, these steps can collide.

## Target model

Move all OS/Python dependency installation to image build/deploy time.
Run startup should only:

1. pull immutable image
2. clone code (if needed for runtime source)
3. execute flow

No `apt-get` or environment-wide `pip install` in per-run startup path.

## Recommended rollout

### Phase 1: stabilize quickly

1. Keep API/config image build in `docker/Dockerfile`.
2. Build worker runtime from a dedicated `docker/Dockerfile.worker` (based on `prefecthq/prefect:3-latest`).
3. Ensure all flow/runtime deps are installed in the worker image:
   - OS libs currently installed in `prefect.yaml.in` shell step
   - Python deps currently installed via `pip_install_requirements`
   - flow code currently pulled with `git_clone`
4. Remove or no-op runtime setup steps in `prefect.yaml.in`:
   - remove `apt-get` shell step
   - remove upgrade/install shell step
   - remove `pip_install_requirements` step
   - remove `git_clone` step once code is baked into image

### Phase 2: tighten reproducibility

1. Pin all flow dependencies in a lock file.
2. Build image once per deploy tag.
3. Keep deploy artifact immutable per tag.
4. Add smoke test run after deployment before accepting batch enqueue.

## Operational safeguards

- Keep a fast rollback to last known-good image tag.
- Add clear startup telemetry:
  - image tag
  - deployment tag
  - `pip freeze` snapshot artifact (optional)
- Avoid mutating base env at runtime (`pip install --upgrade`).

## If runtime install must remain temporarily

Use a single-host lock around setup scripts (for example, `flock`) so only one run executes setup at a time. This is a temporary mitigation, not the desired steady state.

## Suggested acceptance criteria

- No `apt-get` invoked during run startup.
- No environment-wide `pip install` invoked during run startup.
- Two back-to-back run submissions no longer trigger lock/install race failures.
- Failure rate for run startup materially drops after rollout.
