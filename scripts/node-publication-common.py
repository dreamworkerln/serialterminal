#!/usr/bin/env python3
"""Общая guarded-логика публикации node observations и run bundles."""

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
CANONICAL_FILES = {
    "report": "REPORT.md",
    "console": "serialterminal.console.log",
    "serialterminal_log": "serialterminal.log",
}


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
        result = run_git(
            main_repo, "diff", "--quiet", "HEAD", "--", path, check=False
        )
        if result.returncode != 0:
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


def _validate_manifest_identity(data: dict[str, Any], identity: RunIdentity) -> None:
    if data.get("schema") != 1:
        raise PublicationError("MANIFEST.json schema must be 1")
    if data.get("observed_at") != expected_observed_at(identity):
        raise PublicationError("MANIFEST.json observed_at does not match RUN identity")
    if data.get("topic") != identity.topic:
        raise PublicationError("MANIFEST.json topic does not match RUN identity")
    if data.get("result") not in RESULTS:
        raise PublicationError(
            "MANIFEST.json result must be PASS, FAIL, BLOCKED or INCONCLUSIVE"
        )


def _validate_revision_section(
    data: dict[str, Any],
    field: str,
    expected_repo: str,
    *,
    allow_unknown: bool,
) -> None:
    section = data.get(field)
    if not isinstance(section, dict):
        raise PublicationError(f"MANIFEST.json {field} must be an object")
    if section.get("repo") != expected_repo:
        raise PublicationError(f"MANIFEST.json {field}.repo is invalid")
    sha = require_string(section.get("sha"), f"{field}.sha")
    if allow_unknown and sha == "unknown":
        return
    if SHA_RE.fullmatch(sha) is None:
        suffix = " or unknown" if allow_unknown else ""
        raise PublicationError(
            f"MANIFEST.json {field}.sha must be exact 40-hex SHA{suffix}"
        )


def _validate_files_mapping(data: dict[str, Any]) -> None:
    files = data.get("files")
    if not isinstance(files, dict):
        raise PublicationError("MANIFEST.json files must be an object")
    if files != CANONICAL_FILES:
        raise PublicationError("MANIFEST.json files mapping is not canonical")


def _validate_observation_manifest(
    data: dict[str, Any], identity: RunIdentity
) -> tuple[str, str | None]:
    observation = data.get("observation")
    if not isinstance(observation, dict):
        raise PublicationError("MANIFEST.json observation must be an object")

    state = observation.get("state")
    if state == "recorded":
        expected_path = f"../../{identity.observation_path}"
        if observation.get("path") != expected_path:
            raise PublicationError(
                "MANIFEST.json recorded observation path does not match RUN identity"
            )
        if "reason" in observation:
            raise PublicationError(
                "MANIFEST.json recorded observation must not contain reason"
            )
        return state, identity.observation_path

    if state == "not-required":
        if observation.get("path") is not None:
            raise PublicationError(
                "MANIFEST.json not-required observation path must be null"
            )
        require_string(observation.get("reason"), "observation.reason")
        return state, None

    raise PublicationError("MANIFEST.json observation.state must be recorded or not-required")


def validate_manifest_data(data: Any, identity: RunIdentity) -> tuple[str, str | None]:
    if not isinstance(data, dict):
        raise PublicationError("MANIFEST.json root must be an object")
    _validate_manifest_identity(data, identity)
    _validate_revision_section(
        data,
        "serialterminal",
        "dreamworkerln/serialterminal",
        allow_unknown=False,
    )
    _validate_revision_section(
        data,
        "firmware",
        "dreamworkerln/lora-sack-protocol",
        allow_unknown=True,
    )
    _validate_files_mapping(data)
    return _validate_observation_manifest(data, identity)


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PublicationError(f"cannot parse {path.name}: {exc}") from exc


def _require_complete_file_set(run_files: set[str]) -> None:
    if run_files == RUN_REQUIRED_FILES:
        return
    missing = sorted(RUN_REQUIRED_FILES - run_files)
    extra = sorted(run_files - RUN_REQUIRED_FILES)
    detail: list[str] = []
    if missing:
        detail.append("missing=" + ",".join(missing))
    if extra:
        detail.append("extra=" + ",".join(extra))
    suffix = ": " + " ".join(detail) if detail else ""
    raise PublicationError("incomplete run bundle" + suffix)


def _validate_run_members(run_dir: Path, identity: RunIdentity) -> None:
    for name in RUN_REQUIRED_FILES:
        path = run_dir / name
        if not path.is_file():
            raise PublicationError(
                f"run member is not a regular file: {identity.run_dir}/{name}"
            )
    if (run_dir / "REPORT.md").stat().st_size == 0:
        raise PublicationError("REPORT.md must not be empty")
    if (run_dir / "serialterminal.log").stat().st_size == 0:
        raise PublicationError("serialterminal.log must not be empty")


def _validate_recorded_observation(
    repo: Path, identity: RunIdentity, observation_path: str
) -> str:
    obs_path = repo / observation_path
    if not obs_path.is_file():
        raise PublicationError("manifest requires matching observation but it is missing")
    pointer = parse_run_pointer(obs_path.read_text(encoding="utf-8"))
    if pointer != identity:
        raise PublicationError("matching observation does not point back to its RUN bundle")
    return observation_path


def validate_complete_run(repo: Path, identity: RunIdentity, run_files: set[str]) -> list[str]:
    _require_complete_file_set(run_files)
    run_dir = repo / identity.run_dir
    _validate_run_members(run_dir, identity)
    state, observation_path = validate_manifest_data(
        load_json_file(run_dir / "MANIFEST.json"), identity
    )
    selected = [f"{identity.run_dir}/{name}" for name in sorted(RUN_REQUIRED_FILES)]

    if state == "recorded":
        if observation_path is None:
            raise PublicationError("recorded observation path is missing")
        selected.append(_validate_recorded_observation(repo, identity, observation_path))
    elif (repo / identity.observation_path).exists():
        raise PublicationError(
            "manifest says observation not-required but matching observation exists"
        )
    return sorted(selected)


def _manifest_from_commit(repo: Path, commit: str, identity: RunIdentity) -> Any:
    path = f"{identity.run_dir}/MANIFEST.json"
    try:
        return json.loads(git_show_text(repo, commit, path))
    except json.JSONDecodeError as exc:
        raise PublicationError(
            f"local-ahead commit {commit} has invalid MANIFEST.json"
        ) from exc


def _validate_commit_run_content(repo: Path, commit: str, identity: RunIdentity) -> None:
    report = git_show_text(repo, commit, f"{identity.run_dir}/REPORT.md")
    forensic = git_show_text(repo, commit, f"{identity.run_dir}/serialterminal.log")
    git_show_text(repo, commit, f"{identity.run_dir}/serialterminal.console.log")
    if not report:
        raise PublicationError(f"local-ahead commit {commit} has empty REPORT.md")
    if not forensic:
        raise PublicationError(f"local-ahead commit {commit} has empty serialterminal.log")


def validate_commit_run(
    repo: Path, commit: str, identity: RunIdentity, added: set[str]
) -> set[str]:
    expected_paths = {f"{identity.run_dir}/{name}" for name in RUN_REQUIRED_FILES}
    if not expected_paths.issubset(added):
        raise PublicationError(
            f"local-ahead commit {commit} contains incomplete RUN {identity.suffix}"
        )

    state, observation_path = validate_manifest_data(
        _manifest_from_commit(repo, commit, identity), identity
    )
    _validate_commit_run_content(repo, commit, identity)
    consumed = set(expected_paths)

    if state == "recorded":
        if observation_path not in added:
            raise PublicationError(
                f"local-ahead commit {commit} is missing matching observation"
            )
        pointer = parse_run_pointer(git_show_text(repo, commit, observation_path))
        if pointer != identity:
            raise PublicationError(
                f"local-ahead commit {commit} observation/run link mismatch"
            )
        consumed.add(observation_path)
    elif identity.observation_path in added:
        raise PublicationError(
            f"local-ahead commit {commit} adds observation despite not-required manifest"
        )
    return consumed


def _local_ahead_commits(repo: Path) -> list[str]:
    commits = [
        line
        for line in run_git(
            repo, "rev-list", "--reverse", f"origin/{OBS_BRANCH}..HEAD"
        ).stdout.splitlines()
        if line
    ]
    if not commits:
        raise PublicationError("branch reports ahead state but no local-ahead commits were found")
    return commits


def _commit_parent(repo: Path, commit: str) -> str:
    fields = run_git(repo, "rev-list", "--parents", "-n", "1", commit).stdout.strip().split()
    if len(fields) != 2:
        raise PublicationError(f"local-ahead commit {commit} must have exactly one parent")
    return fields[1]


def _added_paths(repo: Path, commit: str) -> set[str]:
    parent = _commit_parent(repo, commit)
    raw = run_git(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "-r",
        parent,
        commit,
    ).stdout.splitlines()
    added: set[str] = set()
    for line in filter(None, raw):
        fields = line.split("\t", 1)
        if len(fields) != 2:
            raise PublicationError(f"cannot parse local-ahead commit {commit}")
        status, path = fields
        if status != "A" or not is_allowed_publication_path(path):
            raise PublicationError(
                f"unsafe local-ahead commit {commit}: "
                f"expected append-only publication, found {status} {path}"
            )
        added.add(path)
    return added


def _validate_standalone_ahead(repo: Path, commit: str, paths: set[str]) -> None:
    for path in paths:
        if observation_identity(path) is None:
            raise PublicationError(
                f"unsafe local-ahead commit {commit}: invalid observation path"
            )
        if parse_run_pointer(git_show_text(repo, commit, path)) is not None:
            raise PublicationError(
                f"unsafe local-ahead commit {commit}: run-bound observation published standalone"
            )


def _validate_local_ahead_commit(repo: Path, commit: str) -> None:
    added = _added_paths(repo, commit)
    run_ids = {
        parts[0]
        for path in added
        if (parts := run_path_parts(path)) is not None
    }
    consumed: set[str] = set()
    for identity in sorted(run_ids):
        consumed.update(validate_commit_run(repo, commit, identity, added))
    remaining = added - consumed

    if run_ids and remaining:
        raise PublicationError(
            f"unsafe local-ahead commit {commit}: unrelated additions mixed with RUN publication"
        )
    if not run_ids:
        _validate_standalone_ahead(repo, commit, remaining)


def validate_local_ahead(repo: Path) -> list[str]:
    commits = _local_ahead_commits(repo)
    for commit in commits:
        _validate_local_ahead_commit(repo, commit)
    return commits


def retry_safe_local_ahead(repo: Path) -> list[str]:
    run_git(repo, "fetch", "--quiet", "origin", OBS_BRANCH)
    behind, ahead = branch_counts(repo)
    if behind:
        raise PublicationError(
            f"observation clone remote is ahead/diverged (behind={behind}, ahead={ahead}); "
            "refusing automatic recovery"
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


def _pending_observations(
    repo: Path, untracked: list[str], incomplete: dict[str, str]
) -> tuple[dict[RunIdentity, str], dict[RunIdentity, RunIdentity | None]]:
    observations: dict[RunIdentity, str] = {}
    pointers: dict[RunIdentity, RunIdentity | None] = {}
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
    return observations, pointers


def _pending_run_files(untracked: list[str]) -> dict[RunIdentity, set[str]]:
    run_files: dict[RunIdentity, set[str]] = {}
    for path in untracked:
        parts = run_path_parts(path)
        if parts is None:
            continue
        identity, name = parts
        run_files.setdefault(identity, set()).add(name)
    return run_files


def _complete_pending_runs(
    repo: Path,
    run_files: dict[RunIdentity, set[str]],
    pointers: dict[RunIdentity, RunIdentity | None],
    incomplete: dict[str, str],
) -> dict[RunIdentity, list[str]]:
    complete: dict[RunIdentity, list[str]] = {}
    run_ids = set(run_files)
    run_ids.update(pointer for pointer in pointers.values() if pointer is not None)
    for identity in sorted(run_ids):
        try:
            complete[identity] = validate_complete_run(
                repo, identity, run_files.get(identity, set())
            )
        except (OSError, UnicodeError, PublicationError) as exc:
            incomplete.setdefault(identity.suffix, str(exc))
    return complete


def _standalone_pending_observations(
    observations: dict[RunIdentity, str],
    pointers: dict[RunIdentity, RunIdentity | None],
    incomplete: dict[str, str],
) -> list[str]:
    standalone: list[str] = []
    for identity, path in sorted(observations.items()):
        pointer = pointers.get(identity)
        if pointer is None:
            standalone.append(path)
        elif pointer != identity:
            incomplete.setdefault(
                identity.suffix,
                f"observation points to different RUN identity: {pointer.suffix}",
            )
    return standalone


def classify_pending(repo: Path) -> PendingState:
    untracked = pending_untracked(repo)
    unknown = [path for path in untracked if not is_allowed_publication_path(path)]
    if unknown:
        raise PublicationError(
            "unexpected untracked files in observation clone: " + ", ".join(unknown)
        )

    incomplete: dict[str, str] = {}
    observations, pointers = _pending_observations(repo, untracked, incomplete)
    run_files = _pending_run_files(untracked)
    complete_runs = _complete_pending_runs(repo, run_files, pointers, incomplete)
    standalone = _standalone_pending_observations(observations, pointers, incomplete)
    return PendingState(untracked, standalone, complete_runs, incomplete)


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
        raise PublicationError(
            "staged changes are not exactly the selected new publication artifacts"
        )


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
    pieces = [
        f"{identity}: {reason}"
        for identity, reason in sorted(pending.incomplete.items())
    ]
    return "; pending/incomplete: " + " | ".join(pieces)


def _selection_for_mode(
    mode: str, pending: PendingState
) -> tuple[list[str], list[RunIdentity]]:
    if mode == "observation":
        return sorted(pending.standalone_observations), []
    if mode == "run":
        identities = sorted(pending.complete_runs)
        paths = {
            path
            for identity in identities
            for path in pending.complete_runs[identity]
        }
        return sorted(paths), identities
    raise PublicationError(f"unknown publication mode: {mode}")


def _no_selection_result(
    mode: str, recovered: list[str], repo: Path, pending: PendingState
) -> int:
    if recovered:
        print(f"unpublished local commits pushed: {len(recovered)}")
        print(f"commit: {run_git(repo, 'rev-parse', 'HEAD').stdout.strip()}")
        return 0
    if mode == "observation":
        message = "no standalone observations eligible for publication"
    else:
        message = "no complete run bundles eligible for publication"
    raise PublicationError(message + format_incomplete(pending))


def _push_new_publication(repo: Path, commit_sha: str) -> None:
    push = run_git(repo, "push", "origin", f"HEAD:{OBS_BRANCH}", check=False)
    if push.returncode != 0:
        detail = push.stderr.strip() or push.stdout.strip() or "git push failed"
        raise PublicationError(
            f"local publication commit created but push failed; commit={commit_sha}; {detail}"
        )
    run_git(repo, "fetch", "--quiet", "origin", OBS_BRANCH)


def _print_success(
    mode: str,
    selected: list[str],
    identities: list[RunIdentity],
    commit_sha: str,
) -> None:
    if mode == "observation":
        print(f"observations committed and pushed: {len(selected)}")
        for path in selected:
            print(f"observation: {path}")
    else:
        print(f"runs committed and pushed: {len(identities)}")
        for identity in identities:
            print(f"run: {identity.run_dir}/")
            if identity.observation_path in selected:
                print(f"observation: {identity.observation_path}")
    print(f"commit: {commit_sha}")


def publish(mode: str, main_repo: Path, helper_path: str) -> int:
    require_main_clone(main_repo, helper_path)
    obs_repo = locate_observation_clone(main_repo)
    require_clean_tracked_state(obs_repo)
    recovered = retry_safe_local_ahead(obs_repo)
    require_clean_tracked_state(obs_repo)
    pending = classify_pending(obs_repo)
    selected, identities = _selection_for_mode(mode, pending)
    if not selected:
        return _no_selection_result(mode, recovered, obs_repo, pending)

    stage_exact(obs_repo, selected)
    message = commit_message(mode, identities, selected)
    run_git(obs_repo, "commit", "-m", message, "--", *selected)
    commit_sha = run_git(obs_repo, "rev-parse", "HEAD").stdout.strip()
    _push_new_publication(obs_repo, commit_sha)
    verify_final_state(obs_repo, selected)
    _print_success(mode, selected, identities, commit_sha)
    return 0
