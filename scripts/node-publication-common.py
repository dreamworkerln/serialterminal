#!/usr/bin/env python3
"""Shared validation/publication logic for node observation and run helpers."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAIN_BRANCH = "dev"
OBS_BRANCH = "node_observations"
OBS_REPO_NAME = "serialterminal-observations"
OBS_HELPER_PATH = "scripts/commit-node-observation"
RUN_HELPER_PATH = "scripts/commit-node-run"
COMMON_PATH = "scripts/node-publication-common.py"

OBS_PATH_RE = re.compile(
    r"^observations/OBS_(?P<stamp>\d{8}T\d{6}Z)_(?P<topic>[a-z0-9][a-z0-9-]*)\.md$"
)
RUN_PATH_RE = re.compile(
    r"^runs/RUN_(?P<stamp>\d{8}T\d{6}Z)_(?P<topic>[a-z0-9][a-z0-9-]*)/"
    r"(?P<name>MANIFEST\.json|REPORT\.md|serialterminal\.log|serialterminal\.console\.log)$"
)
RUN_POINTER_RE = re.compile(
    r"^Run bundle:\s+runs/RUN_(?P<stamp>\d{8}T\d{6}Z)_(?P<topic>[a-z0-9][a-z0-9-]*)/\s*$",
    re.MULTILINE,
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_REQUIRED_FILES = {
    "MANIFEST.json",
    "REPORT.md",
    "serialterminal.log",
    "serialterminal.console.log",
}
RESULTS = {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"}


class PublicationError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class RunIdentity:
    stamp: str
    topic: str

    @property
    def suffix(self) -> str:
        return f"{self.stamp}_{self.topic}"

    @property
    def run_dir(self) -> str:
        return f"runs/RUN_{self.suffix}"

    @property
    def observation_path(self) -> str:
        return f"observations/OBS_{self.suffix}.md"


@dataclass
class PendingState:
    untracked: list[str]
    standalone_observations: list[str]
    complete_runs: dict[RunIdentity, list[str]]
    incomplete: dict[str, str]


def run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise PublicationError(f"git {' '.join(args)}: {detail}")
    return result


def nul_paths(raw: str) -> list[str]:
    return [part for part in raw.split("\0") if part]


def observation_identity(path: str) -> RunIdentity | None:
    match = OBS_PATH_RE.fullmatch(path)
    if match is None:
        return None
    return RunIdentity(match.group("stamp"), match.group("topic"))


def run_path_parts(path: str) -> tuple[RunIdentity, str] | None:
    match = RUN_PATH_RE.fullmatch(path)
    if match is None:
        return None
    return RunIdentity(match.group("stamp"), match.group("topic")), match.group("name")


def is_allowed_publication_path(path: str) -> bool:
    return OBS_PATH_RE.fullmatch(path) is not None or RUN_PATH_RE.fullmatch(path) is not None


def require_main_clone(main_repo: Path, helper_path: str) -> None:
    branch = run_git(main_repo, "branch", "--show-current").stdout.strip()
    if branch != MAIN_BRANCH:
        raise PublicationError(
            f"main SerialTerminal clone must be on {MAIN_BRANCH}, found {branch or '<detached>'}"
        )

    for path in (helper_path, COMMON_PATH):
        run_git(main_repo, "ls-files", "--error-unmatch", "--", path)
        if (
            run_git(main_repo, "diff", "--quiet", "HEAD", "--", path, check=False).returncode
            != 0
        ):
            raise PublicationError(
                f"refusing elevated Git workflow because {path} differs from current HEAD"
            )


def locate_observation_clone(main_repo: Path) -> Path:
    obs_repo = main_repo.parent / OBS_REPO_NAME
    if not obs_repo.is_dir() or not (obs_repo / ".git").is_dir():
        raise PublicationError(f"expected independent sibling clone at ../{OBS_REPO_NAME}")

    top = Path(run_git(obs_repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != obs_repo.resolve():
        raise PublicationError("unexpected observation repository root")

    branch = run_git(obs_repo, "branch", "--show-current").stdout.strip()
    if branch != OBS_BRANCH:
        raise PublicationError(
            f"observation clone must be on {OBS_BRANCH}, found {branch or '<detached>'}"
        )

    upstream = run_git(
        obs_repo,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{upstream}",
    ).stdout.strip()
    if upstream != f"origin/{OBS_BRANCH}":
        raise PublicationError(f"expected upstream origin/{OBS_BRANCH}, found {upstream}")
    return obs_repo


def require_clean_tracked_state(repo: Path) -> None:
    if run_git(repo, "diff", "--quiet", check=False).returncode != 0:
        raise PublicationError("observation clone has unstaged tracked changes")
    if run_git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise PublicationError("observation clone already has staged changes")


def branch_counts(repo: Path) -> tuple[int, int]:
    raw = run_git(
        repo,
        "rev-list",
        "--left-right",
        "--count",
        f"origin/{OBS_BRANCH}...HEAD",
    ).stdout.strip().split()
    if len(raw) != 2:
        raise PublicationError("could not determine observation branch relationship")
    return int(raw[0]), int(raw[1])


def git_show_text(repo: Path, revision: str, path: str) -> str:
    return run_git(repo, "show", f"{revision}:{path}").stdout


def parse_run_pointer(text: str) -> RunIdentity | None:
    matches = list(RUN_POINTER_RE.finditer(text))
    if not matches:
        return None
    if len(matches) != 1:
        raise PublicationError("observation contains multiple Run bundle pointers")
    match = matches[0]
    return RunIdentity(match.group("stamp"), match.group("topic"))


def expected_observed_at(identity: RunIdentity) -> str:
    stamp = identity.stamp
    return (
        f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}T"
        f"{stamp[9:11]}:{stamp[11:13]}:{stamp[13:15]}Z"
    )


def require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise PublicationError(f"manifest field {field} must be a non-empty string")
    return value


def validate_manifest_data(data: Any, identity: RunIdentity) -> tuple[str, str | None]:
    if not isinstance(data, dict):
        raise PublicationError("MANIFEST.json root must be an object")
    if data.get("schema") != 1:
        raise PublicationError("MANIFEST.json schema must be 1")
    if data.get("observed_at") != expected_observed_at(identity):
        raise PublicationError("MANIFEST.json observed_at does not match RUN identity")
    if data.get("topic") != identity.topic:
        raise PublicationError("MANIFEST.json topic does not match RUN identity")
    if data.get("result") not in RESULTS:
        raise PublicationError("MANIFEST.json result must be PASS, FAIL, BLOCKED or INCONCLUSIVE")

    serialterminal = data.get("serialterminal")
    if not isinstance(serialterminal, dict):
        raise PublicationError("MANIFEST.json serialterminal must be an object")
    if serialterminal.get("repo") != "dreamworkerln/serialterminal":
        raise PublicationError("MANIFEST.json serialterminal.repo is invalid")
    serialterminal_sha = require_string(serialterminal.get("sha"), "serialterminal.sha")
    if SHA_RE.fullmatch(serialterminal_sha) is None:
        raise PublicationError("MANIFEST.json serialterminal.sha must be an exact 40-hex SHA")

    firmware = data.get("firmware")
    if not isinstance(firmware, dict):
        raise PublicationError("MANIFEST.json firmware must be an object")
    if firmware.get("repo") != "dreamworkerln/lora-sack-protocol":
        raise PublicationError("MANIFEST.json firmware.repo is invalid")
    firmware_sha = require_string(firmware.get("sha"), "firmware.sha")
    if firmware_sha != "unknown" and SHA_RE.fullmatch(firmware_sha) is None:
        raise PublicationError("MANIFEST.json firmware.sha must be exact 40-hex SHA or unknown")

    files = data.get("files")
    if not isinstance(files, dict):
        raise PublicationError("MANIFEST.json files must be an object")
    expected_files = {
        "report": "REPORT.md",
        "console": "serialterminal.console.log",
        "serialterminal_log": "serialterminal.log",
    }
    if files != expected_files:
        raise PublicationError("MANIFEST.json files mapping is not canonical")

    observation = data.get("observation")
    if not isinstance(observation, dict):
        raise PublicationError("MANIFEST.json observation must be an object")
    state = observation.get("state")
    if state == "recorded":
        expected_path = f"../../{identity.observation_path}"
        if observation.get("path") != expected_path:
            raise PublicationError("MANIFEST.json recorded observation path does not match RUN identity")
        if "reason" in observation:
            raise PublicationError("MANIFEST.json recorded observation must not contain reason")
        return state, identity.observation_path
    if state == "not-required":
        if observation.get("path") is not None:
            raise PublicationError("MANIFEST.json not-required observation path must be null")
        require_string(observation.get("reason"), "observation.reason")
        return state, None
    raise PublicationError("MANIFEST.json observation.state must be recorded or not-required")


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"cannot parse {path.name}: {exc}") from exc


def validate_complete_run(repo: Path, identity: RunIdentity, run_files: set[str]) -> list[str]:
    if run_files != RUN_REQUIRED_FILES:
        missing = sorted(RUN_REQUIRED_FILES - run_files)
        extra = sorted(run_files - RUN_REQUIRED_FILES)
        detail = []
        if missing:
            detail.append("missing=" + ",".join(missing))
        if extra:
            detail.append("extra=" + ",".join(extra))
        raise PublicationError("incomplete run bundle" + (": " + " ".join(detail) if detail else ""))

    run_dir = repo / identity.run_dir
    for name in RUN_REQUIRED_FILES:
        path = run_dir / name
        if not path.is_file():
            raise PublicationError(f"run member is not a regular file: {identity.run_dir}/{name}")
    if (run_dir / "REPORT.md").stat().st_size == 0:
        raise PublicationError("REPORT.md must not be empty")
    if (run_dir / "serialterminal.log").stat().st_size == 0:
        raise PublicationError("serialterminal.log must not be empty")

    state, observation_path = validate_manifest_data(
        load_json_file(run_dir / "MANIFEST.json"), identity
    )
    selected = [f"{identity.run_dir}/{name}" for name in sorted(RUN_REQUIRED_FILES)]

    obs_path = repo / identity.observation_path
    if state == "recorded":
        if not obs_path.is_file():
            raise PublicationError("manifest requires matching observation but it is missing")
        pointer = parse_run_pointer(obs_path.read_text(encoding="utf-8"))
        if pointer != identity:
            raise PublicationError("matching observation does not point back to its RUN bundle")
        selected.append(observation_path or identity.observation_path)
    elif obs_path.exists():
        raise PublicationError("manifest says observation not-required but matching observation exists")
    return sorted(selected)


def validate_commit_run(repo: Path, commit: str, identity: RunIdentity, added: set[str]) -> set[str]:
    expected_run_paths = {f"{identity.run_dir}/{name}" for name in RUN_REQUIRED_FILES}
    if not expected_run_paths.issubset(added):
        raise PublicationError(f"local-ahead commit {commit} contains incomplete RUN {identity.suffix}")

    try:
        data = json.loads(git_show_text(repo, commit, f"{identity.run_dir}/MANIFEST.json"))
    except json.JSONDecodeError as exc:
        raise PublicationError(f"local-ahead commit {commit} has invalid MANIFEST.json") from exc
    state, observation_path = validate_manifest_data(data, identity)

    report = git_show_text(repo, commit, f"{identity.run_dir}/REPORT.md")
    forensic = git_show_text(repo, commit, f"{identity.run_dir}/serialterminal.log")
    git_show_text(repo, commit, f"{identity.run_dir}/serialterminal.console.log")
    if not report:
        raise PublicationError(f"local-ahead commit {commit} has empty REPORT.md")
    if not forensic:
        raise PublicationError(f"local-ahead commit {commit} has empty serialterminal.log")

    consumed = set(expected_run_paths)
    if state == "recorded":
        if observation_path not in added:
            raise PublicationError(f"local-ahead commit {commit} is missing matching observation")
        pointer = parse_run_pointer(git_show_text(repo, commit, observation_path))
        if pointer != identity:
            raise PublicationError(f"local-ahead commit {commit} observation/run link mismatch")
        consumed.add(observation_path)
    elif identity.observation_path in added:
        raise PublicationError(
            f"local-ahead commit {commit} adds observation despite not-required manifest"
        )
    return consumed


def validate_local_ahead(repo: Path) -> list[str]:
    commits = [
        line
        for line in run_git(
            repo, "rev-list", "--reverse", f"origin/{OBS_BRANCH}..HEAD"
        ).stdout.splitlines()
        if line
    ]
    if not commits:
        raise PublicationError("branch reports ahead state but no local-ahead commits were found")

    for commit in commits:
        parent_line = run_git(repo, "rev-list", "--parents", "-n", "1", commit).stdout.strip().split()
        if len(parent_line) != 2:
            raise PublicationError(f"local-ahead commit {commit} must have exactly one parent")
        parent = parent_line[1]
        lines = [
            line
            for line in run_git(
                repo,
                "diff-tree",
                "--no-commit-id",
                "--name-status",
                "-r",
                parent,
                commit,
            ).stdout.splitlines()
            if line
        ]
        added: set[str] = set()
        for line in lines:
            try:
                status, path = line.split("\t", 1)
            except ValueError as exc:
                raise PublicationError(f"cannot parse local-ahead commit {commit}") from exc
            if status != "A" or not is_allowed_publication_path(path):
                raise PublicationError(
                    f"unsafe local-ahead commit {commit}: expected append-only publication, found {status} {path}"
                )
            added.add(path)

        run_ids = {parts[0] for path in added if (parts := run_path_parts(path)) is not None}
        consumed: set[str] = set()
        for identity in sorted(run_ids):
            consumed.update(validate_commit_run(repo, commit, identity, added))

        remaining = added - consumed
        if run_ids:
            if remaining:
                raise PublicationError(
                    f"unsafe local-ahead commit {commit}: unrelated additions mixed with RUN publication"
                )
        else:
            for path in remaining:
                identity = observation_identity(path)
                if identity is None:
                    raise PublicationError(f"unsafe local-ahead commit {commit}: invalid observation path")
                pointer = parse_run_pointer(git_show_text(repo, commit, path))
                if pointer is not None:
                    raise PublicationError(
                        f"unsafe local-ahead commit {commit}: run-bound observation published standalone"
                    )
    return commits


def retry_safe_local_ahead(repo: Path) -> list[str]:
    run_git(repo, "fetch", "--quiet", "origin", OBS_BRANCH)
    behind, ahead = branch_counts(repo)
    if behind:
        raise PublicationError(
            f"observation clone remote is ahead/diverged (behind={behind}, ahead={ahead}); refusing automatic recovery"
        )
    if not ahead:
        return []

    commits = validate_local_ahead(repo)
    head = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    push = run_git(repo, "push", "origin", f"HEAD:{OBS_BRANCH}", check=False)
    if push.returncode != 0:
        detail = push.stderr.strip() or push.stdout.strip() or "git push failed"
        raise PublicationError(
            f"local publication commit exists but push failed; commit={head}; {detail}"
        )
    run_git(repo, "fetch", "--quiet", "origin", OBS_BRANCH)
    if branch_counts(repo) != (0, 0):
        raise PublicationError("retry push completed but local/remote refs are not synchronized")
    return commits


def pending_untracked(repo: Path) -> list[str]:
    return sorted(
        nul_paths(
            run_git(
                repo,
                "ls-files",
                "--others",
                "--exclude-standard",
                "-z",
            ).stdout
        )
    )


def classify_pending(repo: Path) -> PendingState:
    untracked = pending_untracked(repo)
    unknown = [path for path in untracked if not is_allowed_publication_path(path)]
    if unknown:
        raise PublicationError(
            "unexpected untracked files in observation clone: " + ", ".join(unknown)
        )

    observations: dict[RunIdentity, str] = {}
    pointers: dict[RunIdentity, RunIdentity | None] = {}
    incomplete: dict[str, str] = {}
    for path in untracked:
        identity = observation_identity(path)
        if identity is None:
            continue
        if not (repo / path).is_file():
            incomplete[identity.suffix] = f"observation path is not a regular file: {path}"
            continue
        observations[identity] = path
        try:
            pointers[identity] = parse_run_pointer((repo / path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, PublicationError) as exc:
            pointers[identity] = identity
            incomplete[identity.suffix] = str(exc)

    run_files: dict[RunIdentity, set[str]] = {}
    for path in untracked:
        parts = run_path_parts(path)
        if parts is None:
            continue
        identity, name = parts
        run_files.setdefault(identity, set()).add(name)

    complete_runs: dict[RunIdentity, list[str]] = {}
    all_run_ids = set(run_files)
    all_run_ids.update(pointer for pointer in pointers.values() if pointer is not None)
    for identity in sorted(all_run_ids):
        files = run_files.get(identity, set())
        try:
            complete_runs[identity] = validate_complete_run(repo, identity, files)
        except (OSError, UnicodeError, PublicationError) as exc:
            incomplete.setdefault(identity.suffix, str(exc))

    standalone: list[str] = []
    for identity, path in sorted(observations.items()):
        pointer = pointers.get(identity)
        if pointer is None:
            standalone.append(path)
            continue
        if pointer != identity:
            incomplete.setdefault(
                identity.suffix,
                f"observation points to different RUN identity: {pointer.suffix}",
            )

    return PendingState(
        untracked=untracked,
        standalone_observations=standalone,
        complete_runs=complete_runs,
        incomplete=incomplete,
    )


def stage_exact(repo: Path, paths: list[str]) -> None:
    run_git(repo, "add", "--", *paths)
    staged = sorted(
        nul_paths(run_git(repo, "diff", "--cached", "--name-only", "-z").stdout)
    )
    staged_added = sorted(
        nul_paths(
            run_git(
                repo,
                "diff",
                "--cached",
                "--diff-filter=A",
                "--name-only",
                "-z",
            ).stdout
        )
    )
    expected = sorted(paths)
    if staged != expected or staged_added != expected:
        raise PublicationError("staged changes are not exactly the selected new publication artifacts")


def commit_message(mode: str, identities: list[RunIdentity], paths: list[str]) -> str:
    if mode == "observation":
        if len(paths) == 1:
            identity = observation_identity(paths[0])
            if identity is not None:
                return f"obs: {identity.topic.replace('-', ' ')}"
        return "obs: record node observations"
    if len(identities) == 1:
        return f"run: {identities[0].topic.replace('-', ' ')}"
    return "run: record node runs"


def verify_final_state(repo: Path, selected: list[str]) -> None:
    if run_git(repo, "diff", "--quiet", check=False).returncode != 0:
        raise PublicationError("observation clone has tracked changes after publication")
    if run_git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        raise PublicationError("observation clone has staged changes after publication")
    pending = classify_pending(repo)
    still_pending = sorted(set(selected) & set(pending.untracked))
    if still_pending:
        raise PublicationError("published paths are still pending: " + ", ".join(still_pending))
    if branch_counts(repo) != (0, 0):
        raise PublicationError("push completed but local/remote refs are not synchronized")


def format_incomplete(pending: PendingState) -> str:
    if not pending.incomplete:
        return ""
    pieces = [f"{identity}: {reason}" for identity, reason in sorted(pending.incomplete.items())]
    return "; pending/incomplete: " + " | ".join(pieces)


def publish(mode: str, main_repo: Path, helper_path: str) -> int:
    require_main_clone(main_repo, helper_path)
    obs_repo = locate_observation_clone(main_repo)
    require_clean_tracked_state(obs_repo)

    recovered = retry_safe_local_ahead(obs_repo)
    require_clean_tracked_state(obs_repo)
    pending = classify_pending(obs_repo)

    if mode == "observation":
        selected = sorted(pending.standalone_observations)
        identities: list[RunIdentity] = []
        if not selected:
            if recovered:
                print(f"unpublished local commits pushed: {len(recovered)}")
                print(f"commit: {run_git(obs_repo, 'rev-parse', 'HEAD').stdout.strip()}")
                return 0
            raise PublicationError(
                "no standalone observations eligible for publication" + format_incomplete(pending)
            )
    elif mode == "run":
        identities = sorted(pending.complete_runs)
        selected = sorted(
            {path for identity in identities for path in pending.complete_runs[identity]}
        )
        if not selected:
            if recovered:
                print(f"unpublished local commits pushed: {len(recovered)}")
                print(f"commit: {run_git(obs_repo, 'rev-parse', 'HEAD').stdout.strip()}")
                return 0
            raise PublicationError(
                "no complete run bundles eligible for publication" + format_incomplete(pending)
            )
    else:
        raise PublicationError(f"unknown publication mode: {mode}")

    stage_exact(obs_repo, selected)
    run_git(obs_repo, "commit", "-m", commit_message(mode, identities, selected), "--", *selected)
    commit_sha = run_git(obs_repo, "rev-parse", "HEAD").stdout.strip()

    push = run_git(obs_repo, "push", "origin", f"HEAD:{OBS_BRANCH}", check=False)
    if push.returncode != 0:
        detail = push.stderr.strip() or push.stdout.strip() or "git push failed"
        raise PublicationError(
            f"local publication commit created but push failed; commit={commit_sha}; {detail}"
        )
    run_git(obs_repo, "fetch", "--quiet", "origin", OBS_BRANCH)
    verify_final_state(obs_repo, selected)

    if mode == "observation":
        print(f"observations committed and pushed: {len(selected)}")
        for path in selected:
            print(f"observation: {path}")
    else:
        print(f"runs committed and pushed: {len(identities)}")
        for identity in identities:
            print(f"run: {identity.run_dir}/")
            obs = identity.observation_path
            if obs in selected:
                print(f"observation: {obs}")
    print(f"commit: {commit_sha}")
    return 0
