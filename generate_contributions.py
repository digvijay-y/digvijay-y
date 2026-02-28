#!/usr/bin/env python3
"""
Fetches all merged PRs for a GitHub user via GraphQL,
ranks repos by lines contributed, and writes contributions.svg
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

USERNAME = os.environ.get("GITHUB_USERNAME", "digvijay-y")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def gh_graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "errors" in data:
        raise RuntimeError(data["errors"][0]["message"])
    return data


def fetch_merged_prs(username: str) -> list:
    query = """
    query($login: String!, $cursor: String) {
      user(login: $login) {
        pullRequests(states: MERGED, first: 100, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            additions
            deletions
            repository {
              nameWithOwner
              isPrivate
              viewerPermission
              owner { login }
            }
          }
        }
      }
    }
    """
    all_prs, cursor = [], None
    while True:
        data = gh_graphql(query, {"login": username, "cursor": cursor})
        prs = data["data"]["user"]["pullRequests"]
        all_prs.extend(prs["nodes"])
        if not prs["pageInfo"]["hasNextPage"]:
            break
        cursor = prs["pageInfo"]["endCursor"]
    return all_prs


def aggregate(prs: list, username: str) -> list:
    repos = {}
    for pr in prs:
        repo = pr["repository"]
        if repo["isPrivate"]:
            continue
        key = repo["nameWithOwner"]
        if key not in repos:
            repos[key] = {
                "name": key,
                "lines": 0,
                "permission": repo["viewerPermission"],
                "is_own": repo["owner"]["login"].lower() == username.lower(),
            }
        repos[key]["lines"] += pr["additions"] + pr["deletions"]

    ranked = sorted(repos.values(), key=lambda r: r["lines"], reverse=True)
    return [r for r in ranked if r["lines"] > 0][:10]


def get_status(repo: dict) -> str:
    if repo["is_own"]:
        return "Owner"
    if repo["permission"] in ("ADMIN", "MAINTAIN", "WRITE"):
        return "Collaborator"
    return "Contributor"


def fmt_lines(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


STATUS_STYLE = {
    "Owner":        {"color": "#58a6ff", "dot": "#388bfd", "bg": "#1f3a5f"},
    "Collaborator": {"color": "#3fb950", "dot": "#2ea043", "bg": "#1a3a22"},
    "Contributor":  {"color": "#d29922", "dot": "#bb8009", "bg": "#3a2e10"},
}


def build_svg(repos: list, username: str) -> str:
    W = 540
    ROW_H = 54
    HEADER_H = 82
    FOOTER_H = 38
    H = HEADER_H + len(repos) * ROW_H + FOOTER_H
    max_lines = repos[0]["lines"] if repos else 1
    BAR_MAX = 160

    rows_svg = []
    for i, repo in enumerate(repos):
        y = HEADER_H + i * ROW_H
        bg = "#0d1117" if i % 2 == 0 else "#111820"
        parts = repo["name"].split("/", 1)
        org = parts[0] if len(parts) == 2 else ""
        name = parts[1] if len(parts) == 2 else parts[0]
        status = get_status(repo)
        st = STATUS_STYLE[status]
        bar_w = max(6, int((repo["lines"] / max_lines) * BAR_MAX))

        rows_svg.append(f"""
  <rect x="0" y="{y}" width="{W}" height="{ROW_H}" fill="{bg}"/>
  <line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="#21262d" stroke-width="1"/>
  <text y="{y+22}" font-size="12" font-family="ui-monospace,'Cascadia Code','Fira Mono',monospace">
    <tspan x="20" fill="#6e7681">{org}{"/" if org else ""}</tspan><tspan fill="#e6edf3" font-weight="600">{name}</tspan>
  </text>
  <rect x="20" y="{y+32}" width="{bar_w}" height="4" rx="2" fill="{st['color']}" opacity="0.3"/>
  <rect x="20" y="{y+32}" width="{max(3, bar_w//3)}" height="4" rx="2" fill="{st['color']}" opacity="0.85"/>
  <text x="{20+bar_w+8}" y="{y+38}" font-size="10" font-family="ui-monospace,monospace" fill="#484f58">{fmt_lines(repo['lines'])} lines</text>
  <rect x="420" y="{y+15}" width="100" height="24" rx="12" fill="{st['bg']}" stroke="{st['color']}50" stroke-width="1"/>
  <circle cx="436" cy="{y+27}" r="3.5" fill="{st['dot']}"/>
  <text x="444" y="{y+31}" font-size="11" font-family="'Segoe UI',system-ui,sans-serif" font-weight="600" fill="{st['color']}">{status}</text>""")

    now = datetime.utcnow().strftime("%b %d, %Y")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#238636"/>
      <stop offset="50%" stop-color="#1f6feb"/>
      <stop offset="100%" stop-color="#8957e5"/>
    </linearGradient>
    <clipPath id="c"><rect width="{W}" height="{H}" rx="13"/></clipPath>
  </defs>
  <rect width="{W}" height="{H}" rx="13" fill="#0d1117"/>
  <g clip-path="url(#c)">
    <rect x="0" y="0" width="{W}" height="3" fill="url(#g)"/>
    <rect x="0" y="3" width="{W}" height="{HEADER_H-3}" fill="#0d1117"/>
    <text x="20" y="32" font-size="16" font-weight="700" font-family="'Segoe UI',system-ui,sans-serif" fill="#e6edf3">⚡ Open Source Contributions</text>
    <text x="20" y="54" font-size="11" font-family="'Segoe UI',system-ui,sans-serif" fill="#484f58">@{username} · ranked by lines contributed · merged PRs only</text>
    <text x="20" y="{HEADER_H-10}" font-size="9.5" font-family="ui-monospace,monospace" fill="#30363d" letter-spacing="0.8">REPOSITORY</text>
    <text x="470" y="{HEADER_H-10}" font-size="9.5" font-family="ui-monospace,monospace" fill="#30363d" letter-spacing="0.8" text-anchor="middle">ROLE</text>
    {"".join(rows_svg)}
    <rect x="0" y="{H-FOOTER_H}" width="{W}" height="{FOOTER_H}" fill="#090c10"/>
    <line x1="0" y1="{H-FOOTER_H}" x2="{W}" y2="{H-FOOTER_H}" stroke="#21262d" stroke-width="1"/>
    <text x="{W//2}" y="{H-14}" font-size="10" font-family="'Segoe UI',system-ui,sans-serif" fill="#30363d" text-anchor="middle">Auto-updated {now} UTC · github.com/{username}</text>
  </g>
  <rect width="{W}" height="{H}" rx="13" fill="none" stroke="#30363d" stroke-width="1"/>
</svg>"""


def main():
    if not TOKEN:
        print("ERROR: GITHUB_TOKEN is not set", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching merged PRs for @{USERNAME}...")
    prs = fetch_merged_prs(USERNAME)
    print(f"  Found {len(prs)} merged PRs")

    repos = aggregate(prs, USERNAME)
    if not repos:
        print("No public merged PRs found!", file=sys.stderr)
        sys.exit(1)

    print(f"  Top {len(repos)} repos:")
    for r in repos:
        print(f"    {r['name']:40s} {fmt_lines(r['lines']):>8s} lines  {get_status(r)}")

    svg = build_svg(repos, USERNAME)
    out = "contributions.svg"
    with open(out, "w") as f:
        f.write(svg)
    print(f"\nWrote {out} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
