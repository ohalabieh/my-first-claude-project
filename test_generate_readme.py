"""
Unit tests for generate_readme.py.

Tests target the ohalabieh/my-first-claude-project repo. GitHub API calls are
mocked with realistic data so the suite runs offline. The Claude API call is
also mocked.
"""

import sys
import unittest
from unittest.mock import patch, MagicMock

import generate_readme as gr


OWNER = "ohalabieh"
REPO = "my-first-claude-project"
REPO_URL = f"https://github.com/{OWNER}/{REPO}"

# Realistic fake metadata for ohalabieh/my-first-claude-project
FAKE_META = {
    "name": REPO,
    "owner": {"login": OWNER},
    "default_branch": "main",
    "description": "Claude Code Project",
    "language": "Python",
    "stargazers_count": 0,
    "topics": [],
}

FAKE_TREE = {
    "tree": [
        {"path": "README.md", "type": "blob"},
        {"path": "generate_readme.py", "type": "blob"},
        {"path": "test_generate_readme.py", "type": "blob"},
        {"path": "src", "type": "tree"},
    ]
}

FAKE_README_CONTENTS = {
    "encoding": "base64",
    "size": 42,
    # base64 of "# my-first-claude-project\nClaude Code Project\n"
    "content": "IyBteS1maXJzdC1jbGF1ZGUtcHJvamVjdApDbGF1ZGUgQ29kZSBQcm9qZWN0Cg==",
}


# ---------------------------------------------------------------------------
# parse_github_url
# ---------------------------------------------------------------------------

class TestParseGithubUrl(unittest.TestCase):
    def test_https_url(self):
        owner, repo = gr.parse_github_url(REPO_URL)
        self.assertEqual(owner, OWNER)
        self.assertEqual(repo, REPO)

    def test_git_suffix_stripped(self):
        owner, repo = gr.parse_github_url(f"{REPO_URL}.git")
        self.assertEqual(repo, REPO)

    def test_invalid_url_raises(self):
        with self.assertRaises(ValueError):
            gr.parse_github_url("https://example.com/owner/repo")


# ---------------------------------------------------------------------------
# is_readable_file
# ---------------------------------------------------------------------------

class TestIsReadableFile(unittest.TestCase):
    def test_python_file(self):
        self.assertTrue(gr.is_readable_file("src/main.py"))

    def test_node_modules_skipped(self):
        self.assertFalse(gr.is_readable_file("node_modules/lodash/index.js"))

    def test_image_skipped(self):
        self.assertFalse(gr.is_readable_file("assets/logo.png"))

    def test_markdown_readable(self):
        self.assertTrue(gr.is_readable_file("README.md"))

    def test_dot_lock_skipped(self):
        self.assertFalse(gr.is_readable_file("poetry.lock"))

    def test_minified_js_skipped(self):
        self.assertFalse(gr.is_readable_file("dist/bundle.min.js"))


# ---------------------------------------------------------------------------
# fetch_repo_metadata  (mocked)
# ---------------------------------------------------------------------------

class TestFetchRepoMetadata(unittest.TestCase):
    @patch("generate_readme.github_api_get", return_value=FAKE_META)
    def test_returns_expected_fields(self, _mock):
        meta = gr.fetch_repo_metadata(OWNER, REPO, None)
        self.assertEqual(meta["name"], REPO)
        self.assertEqual(meta["owner"]["login"], OWNER)
        self.assertIn("default_branch", meta)

    @patch("generate_readme.github_api_get", return_value=FAKE_META)
    def test_default_branch_is_main(self, _mock):
        meta = gr.fetch_repo_metadata(OWNER, REPO, None)
        self.assertEqual(meta["default_branch"], "main")


# ---------------------------------------------------------------------------
# fetch_tree  (mocked)
# ---------------------------------------------------------------------------

class TestFetchTree(unittest.TestCase):
    @patch("generate_readme.github_api_get")
    def test_tree_contains_readme(self, mock_api):
        mock_api.side_effect = [FAKE_META, FAKE_TREE]
        tree = gr.fetch_tree(OWNER, REPO, None)
        paths = [item["path"] for item in tree]
        self.assertIn("README.md", paths)

    @patch("generate_readme.github_api_get")
    def test_tree_contains_script(self, mock_api):
        mock_api.side_effect = [FAKE_META, FAKE_TREE]
        tree = gr.fetch_tree(OWNER, REPO, None)
        paths = [item["path"] for item in tree]
        self.assertIn("generate_readme.py", paths)

    @patch("generate_readme.github_api_get")
    def test_tree_items_have_type(self, mock_api):
        mock_api.side_effect = [FAKE_META, FAKE_TREE]
        tree = gr.fetch_tree(OWNER, REPO, None)
        self.assertTrue(all("type" in item for item in tree))


# ---------------------------------------------------------------------------
# fetch_file_content  (mocked)
# ---------------------------------------------------------------------------

class TestFetchFileContent(unittest.TestCase):
    @patch("generate_readme.github_api_get", return_value=FAKE_README_CONTENTS)
    def test_fetch_readme_content(self, _mock):
        content = gr.fetch_file_content(OWNER, REPO, "README.md", None)
        self.assertIsNotNone(content)
        self.assertIn("my-first-claude-project", content)

    @patch("generate_readme.github_api_get", side_effect=Exception("404"))
    def test_fetch_nonexistent_file_returns_none(self, _mock):
        content = gr.fetch_file_content(OWNER, REPO, "does_not_exist.xyz", None)
        self.assertIsNone(content)

    @patch("generate_readme.github_api_get", return_value={"encoding": "base64", "size": 100_000, "content": ""})
    def test_large_file_returns_size_message(self, _mock):
        content = gr.fetch_file_content(OWNER, REPO, "big.py", None)
        self.assertIsNotNone(content)
        self.assertIn("too large", content)


# ---------------------------------------------------------------------------
# collect_repo_context  (mocked)
# ---------------------------------------------------------------------------

class TestCollectRepoContext(unittest.TestCase):
    @patch("generate_readme.fetch_file_content", return_value="# my-first-claude-project\n")
    @patch("generate_readme.github_api_get")
    def test_context_contains_repo_name(self, mock_api, _mock_content):
        # collect_repo_context calls github_api_get 3 times:
        #   1. fetch_repo_metadata (direct)
        #   2. fetch_repo_metadata inside fetch_tree
        #   3. git trees endpoint inside fetch_tree
        mock_api.side_effect = [FAKE_META, FAKE_META, FAKE_TREE]
        context = gr.collect_repo_context(OWNER, REPO, None, max_files=5)
        self.assertIn(f"{OWNER}/{REPO}", context)

    @patch("generate_readme.fetch_file_content", return_value="# my-first-claude-project\n")
    @patch("generate_readme.github_api_get")
    def test_context_contains_file_tree_section(self, mock_api, _mock_content):
        mock_api.side_effect = [FAKE_META, FAKE_META, FAKE_TREE]
        context = gr.collect_repo_context(OWNER, REPO, None, max_files=5)
        self.assertIn("File tree:", context)

    @patch("generate_readme.fetch_file_content", return_value="# my-first-claude-project\n")
    @patch("generate_readme.github_api_get")
    def test_context_contains_file_contents_section(self, mock_api, _mock_content):
        mock_api.side_effect = [FAKE_META, FAKE_META, FAKE_TREE]
        context = gr.collect_repo_context(OWNER, REPO, None, max_files=5)
        self.assertIn("File contents", context)

    @patch("generate_readme.fetch_file_content", return_value="# my-first-claude-project\n")
    @patch("generate_readme.github_api_get")
    def test_readme_is_prioritised(self, mock_api, _mock_content):
        mock_api.side_effect = [FAKE_META, FAKE_META, FAKE_TREE]
        context = gr.collect_repo_context(OWNER, REPO, None, max_files=5)
        readme_pos = context.find("--- README.md ---")
        script_pos = context.find("--- generate_readme.py ---")
        # README should appear before generate_readme.py (priority ordering)
        self.assertGreater(script_pos, readme_pos)


# ---------------------------------------------------------------------------
# generate_readme_with_claude  (mocked)
# ---------------------------------------------------------------------------

class TestGenerateReadmeWithClaude(unittest.TestCase):
    def test_returns_claude_response(self):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="# Generated README\nHello world")]
        mock_client.messages.create.return_value = mock_message

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            result = gr.generate_readme_with_claude("some repo context")

        self.assertEqual(result, "# Generated README\nHello world")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-6")
        self.assertIn("some repo context", call_kwargs["messages"][0]["content"])

    def test_prompt_includes_readme_instructions(self):
        mock_anthropic = MagicMock()
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="# README")]
        mock_client.messages.create.return_value = mock_message

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            gr.generate_readme_with_claude("ctx")

        prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
        self.assertIn("README", prompt)
        self.assertIn("installation", prompt.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
