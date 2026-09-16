from __future__ import annotations

from test_node_publication import git, remote_head, repos, run_helper, write_run


def test_run_helper_publishes_optional_auxiliary_artifact(repos):
    main, obs, remote = repos
    suffix = "20260916T001000Z_with-artifact"
    selected = write_run(obs, suffix, observation="not-required")
    artifact = obs / f"runs/RUN_{suffix}/artifacts/btmon.log"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"btmon\x00exact\n")
    artifact_path = str(artifact.relative_to(obs))

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    for path in selected + [artifact_path]:
        assert git(obs, "ls-files", path).stdout.strip() == path
    committed = git(obs, "show", "--format=", "--name-only", "HEAD").stdout.splitlines()
    assert artifact_path in committed
    assert remote_head(remote) == git(obs, "rev-parse", "HEAD").stdout.strip()


def test_run_helper_rejects_auxiliary_file_outside_artifacts_namespace(repos):
    main, obs, _ = repos
    suffix = "20260916T001100Z_bad-artifact-path"
    write_run(obs, suffix, observation="not-required")
    bad = obs / f"runs/RUN_{suffix}/btmon.log"
    bad.write_text("capture\n", encoding="utf-8")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 1
    assert "unexpected untracked files" in result.stderr
    assert not git(obs, "ls-files", str(bad.relative_to(obs))).stdout.strip()


def test_failed_push_with_auxiliary_artifact_is_retry_safe(repos):
    main, obs, remote = repos
    suffix = "20260916T001200Z_artifact-retry"
    write_run(obs, suffix, observation="not-required")
    artifact = obs / f"runs/RUN_{suffix}/artifacts/btmon.log"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("capture\n", encoding="utf-8")
    artifact_path = str(artifact.relative_to(obs))

    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    failed = run_helper(main, "commit-node-run")

    assert failed.returncode == 1
    assert "local publication commit created but push failed" in failed.stderr
    assert git(obs, "ls-files", artifact_path).stdout.strip() == artifact_path
    assert git(obs, "rev-list", "--count", "origin/node_observations..HEAD").stdout.strip() == "1"

    hook.unlink()
    retried = run_helper(main, "commit-node-run")

    assert retried.returncode == 0, retried.stderr
    assert "unpublished local commits pushed: 1" in retried.stdout
    assert remote_head(remote) == git(obs, "rev-parse", "HEAD").stdout.strip()
