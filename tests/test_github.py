import unittest
from unittest.mock import patch

from sm64_builder.github import (
    Commit,
    describe_commit,
    list_ios_commits,
    validate_repository,
)


class GitHubTests(unittest.TestCase):
    def test_validates_repository_names(self):
        self.assertEqual(validate_repository("n64decomp/sm64.git"), "n64decomp/sm64")
        with self.assertRaisesRegex(ValueError, "owner/name"):
            validate_repository("https://github.com/n64decomp/sm64")

    @patch("sm64_builder.github._request_json")
    def test_lists_ios_commits_on_selected_branch(self, request_json):
        request_json.return_value = [
            {
                "sha": "a" * 40,
                "commit": {
                    "message": "Add iOS target\nDetails",
                    "author": {"name": "Builder", "date": "2025-01-01T00:00:00Z"},
                },
            },
            {"sha": "b" * 40, "commit": {"message": "", "author": None}},
        ]
        commits = list_ios_commits("owner/repo", "ios-branch")
        self.assertEqual(
            commits,
            [
                Commit("a" * 40, "Add iOS target", "Builder", "2025-01-01T00:00:00Z"),
                Commit("b" * 40, "(no commit message)", "Unknown", ""),
            ],
        )
        self.assertIn("sha=ios-branch", request_json.call_args.args[0])
        self.assertIn("path=src%2Fios", request_json.call_args.args[0])

    @patch("sm64_builder.github._request_json")
    def test_describes_changed_files_and_patch(self, request_json):
        request_json.return_value = {
            "commit": {"message": "Fix iOS rendering"},
            "files": [
                {
                    "filename": "src/ios/gfx.m",
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
        }
        description = describe_commit("owner/repo", "a" * 40)
        self.assertIn("Fix iOS rendering", description)
        self.assertIn("src/ios/gfx.m", description)
        self.assertIn("+new", description)


if __name__ == "__main__":
    unittest.main()
