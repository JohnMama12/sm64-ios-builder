import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List


_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_API_ROOT = "https://api.github.com"


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str
    author: str
    date: str

    @property
    def short_sha(self) -> str:
        return self.sha[:8]


class GitHubError(RuntimeError):
    pass


def validate_repository(repository: str) -> str:
    repository = repository.strip().removesuffix(".git")
    if not _REPOSITORY_PATTERN.fullmatch(repository):
        raise ValueError("Enter a GitHub repository as owner/name.")
    return repository


def _request_json(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "sm64-ios-builder",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise GitHubError(
            "GitHub API returned HTTP %d: %s" % (error.code, detail[:500])
        ) from error
    except urllib.error.URLError as error:
        raise GitHubError("Cannot reach GitHub: %s" % error.reason) from error


def list_branches(repository: str) -> List[str]:
    repository = validate_repository(repository)
    url = "%s/repos/%s/branches?per_page=100" % (_API_ROOT, repository)
    branches = _request_json(url)
    if not isinstance(branches, list):
        raise GitHubError("Unexpected branch list returned by GitHub.")
    return [entry["name"] for entry in branches if "name" in entry]


def list_ios_commits(repository: str, branch: str) -> List[Commit]:
    repository = validate_repository(repository)
    query = urllib.parse.urlencode(
        {"sha": branch, "path": "src/ios", "per_page": 100}
    )
    url = "%s/repos/%s/commits?%s" % (_API_ROOT, repository, query)
    records = _request_json(url)
    if not isinstance(records, list):
        raise GitHubError("Unexpected commit list returned by GitHub.")
    commits = []
    for record in records:
        commit = record.get("commit", {})
        author = commit.get("author") or {}
        message_lines = commit.get("message", "").splitlines()
        commits.append(
            Commit(
                sha=record["sha"],
                message=message_lines[0] if message_lines else "(no commit message)",
                author=author.get("name", "Unknown"),
                date=author.get("date", ""),
            )
        )
    return commits


def describe_commit(repository: str, sha: str) -> str:
    repository = validate_repository(repository)
    url = "%s/repos/%s/commits/%s" % (
        _API_ROOT,
        repository,
        urllib.parse.quote(sha, safe=""),
    )
    record: Dict = _request_json(url)
    commit = record.get("commit", {})
    message = commit.get("message", "(no commit message)")
    files = record.get("files", [])
    output = [message, "", "Changed files:"]
    for item in files:
        output.append(
            "  %s  %s" % (item.get("status", "modified"), item.get("filename", ""))
        )
        patch = item.get("patch")
        if patch:
            lines = patch.splitlines()
            output.extend("    " + line for line in lines[:12])
            if len(lines) > 12:
                output.append("    ...")
    if not files:
        output.append("  (GitHub did not include file details.)")
    return "\n".join(output)
