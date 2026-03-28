"""
Flask web server for the README generator.

Serves the UI and exposes a /generate endpoint that calls generate_readme.py.
"""

import os
from flask import Flask, render_template, request, jsonify

import generate_readme as gr

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    repo_url = (data or {}).get("url", "").strip()

    if not repo_url:
        return jsonify({"error": "No URL provided."}), 400

    try:
        owner, repo = gr.parse_github_url(repo_url)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    token = os.environ.get("GITHUB_TOKEN")

    try:
        context = gr.collect_repo_context(owner, repo, token)
    except Exception as e:
        return jsonify({"error": f"Failed to fetch repository data: {e}"}), 502

    try:
        readme = gr.generate_readme_with_claude(context)
    except Exception as e:
        return jsonify({"error": f"Failed to generate README: {e}"}), 502

    return jsonify({"readme": readme})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
