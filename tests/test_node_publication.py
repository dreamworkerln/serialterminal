from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
ST_SHA = "a" * 40
FW_SHA = "b" * 40


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result


def configure(repo: Path) -> None:
    git(repo, "config", "user.email", "tests@example.invalid")
    git(repo, "config", "user.name", "Publication Tests")


@pytest.fixture
def repos(tmp_path: Path):
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    seed = tmp_path / "seed"
    seed.mkdir()
    git(seed, "init")
    configure(seed)
    git(seed, "checkout", "-b", "node_observations")
    (seed / "REVIEW_STATE.md").write_text("# review\n", encoding="utf-8")
    git(seed, "add", "REVIEW_STATE.md")
    git(seed, "commit", "-m", "init observations")
    git(seed, "remote", "add", "origin", str(remote))
    git(seed, "push", "-u", "origin", "node_observations")

    main = tmp_path / "serialterminal"
    main.mkdir()
    git(main, "init")
    configure(main)
    git(main, "checkout", "-b", "dev")
    (main / "scripts").mkdir()
    for name in (
        "node-publication-common.py",
        "commit-node-observation",
        "commit-node-run",
    ):
        shutil.copy2(SCRIPT_DIR / name, main / "scripts" / name)
    git(main, "add", "scripts")
    git(main, "commit", "-m", "publication helpers")

    obs = tmp_path / "serialterminal-observations"
    subprocess.run(
        [
            "git",
            "clone",
            "--single-branch",
            "--branch",
            "node_observations",
            str(remote),
            str(obs),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    configure(obs)
    return main, obs, remote


def run_helper(main: Path, name: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", "-I", f"scripts/{name}"],
        cwd=main,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def write_obs(
    obs: Path,
    suffix: str,
    *,
    run_bound: bool = False,
    pointer_suffix: str | None = None,
) -> str:
    path = f"observations/OBS_{suffix}.md"
    target = obs / path
    target.parent.mkdir(parents=True, exist_ok=True)
    text = "# Node observation\n\nResult: PASS\n"
    if run_bound:
        pointer_suffix = pointer_suffix or suffix
        text += f"\nRun bundle: runs/RUN_{pointer_suffix}/\n"
    target.write_text(text, encoding="utf-8")
    return path


def manifest(suffix: str, *, observation: str = "recorded") -> dict:
    stamp, topic = suffix.split("_", 1)
    observed = (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T"
        f"{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
    )
    obs_obj = (
        {"state": "recorded", "path": f"../../observations/OBS_{suffix}.md"}
        if observation == "recorded"
        else {"state": "not-required", "path": None, "reason": "routine run"}
    )
    return {
        "schema": 1,
        "observed_at": observed,
        "topic": topic,
        "result": "PASS",
        "serialterminal": {
            "repo": "dreamworkerln/serialterminal",
            "sha": ST_SHA,
        },
        "firmware": {
            "repo": "dreamworkerln/lora-sack-protocol",
            "sha": FW_SHA,
        },
        "observation": obs_obj,
        "files": {
            "report": "REPORT.md",
            "console": "serialterminal.console.log",
            "serialterminal_log": "serialterminal.log",
        },
    }


def write_run(
    obs: Path,
    suffix: str,
    *,
    observation: str = "recorded",
    valid: bool = True,
) -> list[str]:
    run_dir = obs / f"runs/RUN_{suffix}"
    run_dir.mkdir(parents=True, exist_ok=True)
    data = manifest(suffix, observation=observation)
    if not valid:
        data["topic"] = "wrong-topic"
    (run_dir / "MANIFEST.json").write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "REPORT.md").write_text("# Run report\n\nPASS\n", encoding="utf-8")
    (run_dir / "serialterminal.log").write_text("forensic\n", encoding="utf-8")
    (run_dir / "serialterminal.console.log").write_text("console\n", encoding="utf-8")
    paths = [str(path.relative_to(obs)) for path in sorted(run_dir.iterdir())]
    if observation == "recorded":
        paths.append(write_obs(obs, suffix, run_bound=True))
    return sorted(paths)


def remote_head(remote: Path) -> str:
    result = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-parse", "refs/heads/node_observations"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def test_observation_helper_publishes_multiple_and_ignores_pending_run(repos):
    main, obs, remote = repos
    first = write_obs(obs, "20260908T100000Z_first")
    second = write_obs(obs, "20260908T100100Z_second")
    run_dir = obs / "runs/RUN_20260908T100200Z_incomplete"
    run_dir.mkdir(parents=True)
    (run_dir / "REPORT.md").write_text("draft\n", encoding="utf-8")

    result = run_helper(main, "commit-node-observation")

    assert result.returncode == 0, result.stderr
    assert "observations committed and pushed: 2" in result.stdout
    assert (obs / first).exists() and (obs / second).exists()
    assert git(obs, "ls-files", first).stdout.strip() == first
    assert git(obs, "ls-files", second).stdout.strip() == second
    run_report = "runs/RUN_20260908T100200Z_incomplete/REPORT.md"
    assert not git(obs, "ls-files", run_report).stdout.strip()
    assert remote_head(remote) == git(obs, "rev-parse", "HEAD").stdout.strip()


def test_observation_helper_does_not_publish_run_bound_observation(repos):
    main, obs, _ = repos
    path = write_obs(obs, "20260908T101000Z_bound", run_bound=True)

    result = run_helper(main, "commit-node-observation")

    assert result.returncode == 1
    assert "no standalone observations eligible for publication" in result.stderr
    assert not git(obs, "ls-files", path).stdout.strip()


def test_run_helper_publishes_recorded_run_and_leaves_standalone_obs(repos):
    main, obs, remote = repos
    suffix = "20260908T102000Z_complete"
    selected = write_run(obs, suffix, observation="recorded")
    standalone = write_obs(obs, "20260908T102100Z_standalone")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    assert "runs committed and pushed: 1" in result.stdout
    for path in selected:
        assert git(obs, "ls-files", path).stdout.strip() == path
    assert not git(obs, "ls-files", standalone).stdout.strip()
    assert (obs / standalone).exists()
    assert remote_head(remote) == git(obs, "rev-parse", "HEAD").stdout.strip()


def test_run_helper_publishes_run_without_observation(repos):
    main, obs, _ = repos
    suffix = "20260908T103000Z_no-observation"
    selected = write_run(obs, suffix, observation="not-required")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    for path in selected:
        assert git(obs, "ls-files", path).stdout.strip() == path
    assert not (obs / f"observations/OBS_{suffix}.md").exists()


def test_incomplete_run_does_not_block_complete_run(repos):
    main, obs, _ = repos
    incomplete = obs / "runs/RUN_20260908T104000Z_old"
    incomplete.mkdir(parents=True)
    (incomplete / "REPORT.md").write_text("partial\n", encoding="utf-8")
    suffix = "20260908T104100Z_new"
    selected = write_run(obs, suffix, observation="not-required")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    for path in selected:
        assert git(obs, "ls-files", path).stdout.strip() == path
    assert (incomplete / "REPORT.md").exists()
    report = str((incomplete / "REPORT.md").relative_to(obs))
    assert not git(obs, "ls-files", report).stdout.strip()


def test_invalid_run_does_not_block_other_complete_run(repos):
    main, obs, _ = repos
    write_run(obs, "20260908T105000Z_bad", observation="not-required", valid=False)
    suffix = "20260908T105100Z_good"
    write_run(obs, suffix, observation="not-required")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    assert git(obs, "ls-files", f"runs/RUN_{suffix}/MANIFEST.json").stdout.strip()
    bad_manifest = "runs/RUN_20260908T105000Z_bad/MANIFEST.json"
    assert not git(obs, "ls-files", bad_manifest).stdout.strip()


def test_unknown_untracked_file_blocks_both_helpers(repos):
    main, obs, _ = repos
    write_obs(obs, "20260908T106000Z_ok")
    (obs / "junk.txt").write_text("junk\n", encoding="utf-8")

    for helper in ("commit-node-observation", "commit-node-run"):
        result = run_helper(main, helper)
        assert result.returncode == 1
        assert "unexpected untracked files" in result.stderr


def test_tracked_history_modification_blocks_publication(repos):
    main, obs, _ = repos
    (obs / "REVIEW_STATE.md").write_text("changed\n", encoding="utf-8")
    write_obs(obs, "20260908T107000Z_ok")

    result = run_helper(main, "commit-node-observation")

    assert result.returncode == 1
    assert "unstaged tracked changes" in result.stderr


def test_failed_push_is_retried_then_new_backlog_is_published(repos):
    main, obs, remote = repos
    first = write_obs(obs, "20260908T108000Z_first")
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    failed = run_helper(main, "commit-node-observation")

    assert failed.returncode == 1
    assert "local publication commit created but push failed" in failed.stderr
    assert git(obs, "rev-list", "--count", "origin/node_observations..HEAD").stdout.strip() == "1"
    assert git(obs, "ls-files", first).stdout.strip() == first

    hook.unlink()
    second = write_obs(obs, "20260908T108100Z_second")
    retried = run_helper(main, "commit-node-observation")

    assert retried.returncode == 0, retried.stderr
    assert "observations committed and pushed: 1" in retried.stdout
    assert git(obs, "ls-files", second).stdout.strip() == second
    relation = git(
        obs,
        "rev-list",
        "--left-right",
        "--count",
        "origin/node_observations...HEAD",
    ).stdout.split()
    assert relation == ["0", "0"]
    assert remote_head(remote) == git(obs, "rev-parse", "HEAD").stdout.strip()


def test_divergence_after_failed_push_is_hard_failure(repos, tmp_path: Path):
    main, obs, remote = repos
    write_obs(obs, "20260908T109000Z_local")
    hook = remote / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    failed = run_helper(main, "commit-node-observation")
    assert failed.returncode == 1
    hook.unlink()

    other = tmp_path / "other"
    subprocess.run(
        [
            "git",
            "clone",
            "--single-branch",
            "--branch",
            "node_observations",
            str(remote),
            str(other),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    configure(other)
    (other / "observations").mkdir(exist_ok=True)
    remote_obs = other / "observations/OBS_20260908T109100Z_remote.md"
    remote_obs.write_text("# remote\n", encoding="utf-8")
    git(other, "add", str(remote_obs.relative_to(other)))
    git(other, "commit", "-m", "remote observation")
    git(other, "push", "origin", "node_observations")

    result = run_helper(main, "commit-node-observation")

    assert result.returncode == 1
    assert "remote is ahead/diverged" in result.stderr


def test_multiple_complete_runs_publish_together(repos):
    main, obs, _ = repos
    one = "20260908T110000Z_one"
    two = "20260908T110100Z_two"
    write_run(obs, one, observation="recorded")
    write_run(obs, two, observation="not-required")

    result = run_helper(main, "commit-node-run")

    assert result.returncode == 0, result.stderr
    assert "runs committed and pushed: 2" in result.stdout
    assert git(obs, "ls-files", f"runs/RUN_{one}/MANIFEST.json").stdout.strip()
    assert git(obs, "ls-files", f"runs/RUN_{two}/MANIFEST.json").stdout.strip()


def test_mismatched_run_pointer_stays_pending_and_does_not_publish_as_standalone(repos):
    main, obs, _ = repos
    path = write_obs(
        obs,
        "20260908T111000Z_mismatch",
        run_bound=True,
        pointer_suffix="20260908T111100Z_other",
    )
    standalone = write_obs(obs, "20260908T111200Z_ok")

    result = run_helper(main, "commit-node-observation")

    assert result.returncode == 0, result.stderr
    assert git(obs, "ls-files", standalone).stdout.strip() == standalone
    assert not git(obs, "ls-files", path).stdout.strip()
