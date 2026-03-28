#!/usr/bin/env python3
"""
Generate a README.md for a GitHub repository using the Claude API.

Usage:
    python generate_readme.py <github_repo_url>

Example:
    python generate_readme.py https://github.com/owner/repo
"""

import sys
import re
import urllib.request
import urllib.error
import json
import os


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub URL."""
    pattern = r"github\.com[:/]([^/]+)/([^/\s.]+?)(?:\.git)?$"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not parse GitHub URL: {url}")
    return match.group(1), match.group(2)


def github_api_get(path: str, token: str | None = None) -> dict | list:
    """Make a GitHub API GET request."""
    url = f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "readme-generator")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def fetch_repo_metadata(owner: str, repo: str, token: str | None) -> dict:
    """Fetch basic repository metadata."""
    return github_api_get(f"/repos/{owner}/{repo}", token)


def fetch_tree(owner: str, repo: str, token: str | None) -> list[dict]:
    """Fetch the full file tree of the default branch."""
    repo_data = fetch_repo_metadata(owner, repo, token)
    branch = repo_data.get("default_branch", "main")
    tree_data = github_api_get(
        f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1", token
    )
    return tree_data.get("tree", [])


def is_readable_file(path: str) -> bool:
    """Return True for text/code files worth reading for context."""
    skip_dirs = {
        ".git", "node_modules", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "vendor", "target",
    }
    parts = path.split("/")
    if any(p in skip_dirs for p in parts):
        return False

    skip_extensions = {
        ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
        ".pdf", ".zip", ".tar", ".gz", ".whl", ".lock",
        ".min.js", ".min.css", ".map",
    }
    lower = path.lower()
    if any(lower.endswith(ext) for ext in skip_extensions):
        return False

    readable_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
        ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
        ".sh", ".bash", ".zsh", ".md", ".txt", ".toml", ".yaml",
        ".yml", ".json", ".xml", ".html", ".css", ".env.example",
        ".dockerfile", "dockerfile", ".gitignore", "makefile",
        "requirements.txt", "package.json", "cargo.toml", "go.mod",
    }
    filename = parts[-1].lower()
    ext = os.path.splitext(filename)[1]
    return ext in readable_extensions or filename in readable_extensions


def fetch_file_content(owner: str, repo: str, path: str, token: str | None) -> str | None:
    """Fetch decoded content of a single file (returns None if too large or binary)."""
    import base64
    try:
        data = github_api_get(f"/repos/{owner}/{repo}/contents/{path}", token)
        if isinstance(data, list) or data.get("encoding") != "base64":
            return None
        size = data.get("size", 0)
        if size > 50_000:  # skip files larger than 50 KB
            return f"[File too large to include: {size} bytes]"
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def collect_repo_context(owner: str, repo: str, token: str | None, max_files: int = 30) -> str:
    """Build a text summary of the repo for the AI prompt."""
    meta = fetch_repo_metadata(owner, repo, token)
    lines = [
        f"Repository: {owner}/{repo}",
        f"Description: {meta.get('description') or 'None'}",
        f"Language: {meta.get('language') or 'Unknown'}",
        f"Stars: {meta.get('stargazers_count', 0)}",
        f"Topics: {', '.join(meta.get('topics', [])) or 'None'}",
        "",
    ]

    tree = fetch_tree(owner, repo, token)
    file_paths = [item["path"] for item in tree if item["type"] == "blob"]

    lines.append("File tree:")
    for p in file_paths[:200]:
        lines.append(f"  {p}")
    lines.append("")

    # Prioritise important files
    priority_names = {
        "readme.md", "readme.rst", "readme.txt",
        "package.json", "setup.py", "setup.cfg", "pyproject.toml",
        "cargo.toml", "go.mod", "requirements.txt", "makefile",
        "dockerfile", ".env.example", "main.py", "main.go",
        "index.js", "index.ts", "app.py", "app.js",
    }

    readable = [p for p in file_paths if is_readable_file(p)]
    priority = [p for p in readable if os.path.basename(p).lower() in priority_names]
    rest = [p for p in readable if p not in priority]
    selected = (priority + rest)[:max_files]

    lines.append(f"File contents (up to {max_files} files):")
    for path in selected:
        content = fetch_file_content(owner, repo, path, token)
        if content is not None:
            lines.append(f"\n--- {path} ---")
            lines.append(content[:3000])  # cap per-file content

    return "\n".join(lines)


def generate_readme_with_claude(context: str) -> str:
    """Call the Claude API to generate a README from repo context."""
    import anthropic

    client = anthropic.Anthropic()
    prompt = (
        "You are a technical writer. Based on the repository context below, "
        "generate a comprehensive, well-structured README.md in Markdown format.\n\n"
        "Include sections such as: project title and description, features, "
        "requirements/prerequisites, installation, usage, configuration (if relevant), "
        "project structure (if helpful), contributing guidelines, and license.\n\n"
        "Use clear language and practical examples. Do not invent details not "
        "supported by the code—if something is unclear, note it briefly.\n\n"
        f"Repository context:\n{context}"
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_readme.py <github_repo_url>")
        print("Example: python generate_readme.py https://github.com/owner/repo")
        sys.exit(1)

    repo_url = sys.argv[1]
    token = os.environ.get("GITHUB_TOKEN")

    print(f"Fetching repository data from {repo_url}...")
    owner, repo = parse_github_url(repo_url)
    context = collect_repo_context(owner, repo, token)

    print("Generating README with Claude...")
    readme = generate_readme_with_claude(context)

    output_path = "README.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(readme)

    print(f"README written to {output_path}")


if __name__ == "__main__":
    main()
