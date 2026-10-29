from subprocess import run

run(
    [
        "uv",
        "run",
        "python",
        "scripts/research_status_digest.py",
    ],
    check=False,
)
