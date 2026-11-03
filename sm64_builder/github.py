import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List


_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_API_ROOT = "https://api.github.com"


@dataclass(frozen=True)
class SourceRelease:
    tag: str
    name: str
    body: str
    published_at: str
    url: str

    @property
    def title(self) -> str:
        return self.name or self.tag


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


def list_source_releases(repository: str) -> List[SourceRelease]:
    repository = validate_repository(repository)
    url = "%s/repos/%s/releases?per_page=100" % (_API_ROOT, repository)
    records = _request_json(url)
    if not isinstance(records, list):
        raise GitHubError("Unexpected release list returned by GitHub.")
    releases = []
    for record in records:
        tag = record.get("tag_name")
        if tag and not record.get("draft", False):
            releases.append(
                SourceRelease(
                    tag=tag,
                    name=record.get("name") or "",
                    body=record.get("body") or "",
                    published_at=record.get("published_at") or "",
                    url=record.get("html_url") or "",
                )
            )
    return releases
