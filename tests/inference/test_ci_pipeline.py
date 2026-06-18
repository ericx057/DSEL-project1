import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _job_section(workflow_text: str, job_name: str) -> str:
    marker = f"  {job_name}:"
    lines = workflow_text.splitlines()
    start = next(index for index, line in enumerate(lines) if line == marker)
    section = []
    for index, line in enumerate(lines[start:]):
        if index > 0 and line.startswith("  ") and not line.startswith("    "):
            break
        section.append(line)
    return "\n".join(section)


def _load_smoke_module():
    path = ROOT / "scripts" / "ci_container_smoke.py"
    spec = importlib.util.spec_from_file_location("ci_container_smoke", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_ci_workflow_runs_container_smoke_before_push_and_reports_digest():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    docker_job = _job_section(workflow, "docker")

    assert "permissions:\n  contents: read\n\njobs:" in workflow
    assert "packages: write" not in workflow.split("jobs:", 1)[0]
    assert "permissions:\n      contents: read\n      packages: write" in docker_job
    assert "load: true" in docker_job
    assert "python scripts/ci_container_smoke.py --image" in docker_job
    assert docker_job.index("python scripts/ci_container_smoke.py --image") < docker_job.index("docker push")
    assert "$GITHUB_STEP_SUMMARY" in docker_job


def test_ci_smoke_script_builds_hs256_jwt_with_expected_claims():
    smoke = _load_smoke_module()

    token = smoke.create_hs256_token(
        subject="ci-user",
        groups=["ci-group"],
        secret="ci-secret",
        issuer="cis",
        audience="developers",
        lifetime_seconds=60,
    )
    header, payload, signature = token.split(".")

    assert header
    assert payload
    assert signature
    decoded = smoke.decode_unverified_payload(token)
    assert decoded["sub"] == "ci-user"
    assert decoded["groups"] == ["ci-group"]
    assert decoded["iss"] == "cis"
    assert decoded["aud"] == "developers"


def test_ci_smoke_script_constructs_docker_run_command_without_openrouter_secret():
    smoke = _load_smoke_module()

    command = smoke.SmokeHarness(image="cis:test", host_port=8123).docker_run_command("cis-data-test")
    command_text = " ".join(command)

    assert "docker" in command[:1]
    assert "--health-cmd" not in command
    assert "-e" in command
    assert "CIS_OPENROUTER_API_KEY=" in command
    assert "CIS_EMBEDDING_BACKEND=hashing" in command
    assert "CIS_BOOTSTRAP_USER=ci-user" in command
    assert "CIS_BOOTSTRAP_GROUP=ci-group" in command
    assert "cis:test" in command
    assert "8123:8000" in command_text
