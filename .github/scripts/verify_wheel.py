"""Build and test the distribution in a fresh venv, independent of src imports."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import venv
import zipfile


def main():
    repo = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix="sdlc-wheel-") as directory:
        work = Path(directory)
        wheels = work / "wheels"
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps",
                        "--wheel-dir", str(wheels), str(repo)], check=True)
        wheel, = wheels.glob("*.whl")
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            assert all(name.startswith(("sdlc_agents/", "sdlc_agents-")) for name in names), names
            assert "sdlc_agents/cli.py" in names
            assert "sdlc_agents/storage/json_store.py" in names
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        subprocess.run([str(python), "-m", "pip", "install", f"{wheel}[dev]"], check=True)
        subprocess.run([str(python), "-m", "pip", "check"], check=True)
        subprocess.run([str(python), "-I", "-c",
                        "import sdlc_agents, sys; from pathlib import Path; "
                        "assert Path(sdlc_agents.__file__).is_relative_to(Path(sys.prefix))"],
                       cwd=work, check=True)
        executable = scripts / ("sdlc-agents.exe" if os.name == "nt" else "sdlc-agents")
        subprocess.run([str(executable), "list", "--agent-root",
                        str(repo / "tests/fixtures/agents")], cwd=work, check=True)
        subprocess.run([str(python), "-I", "-m", "pytest", str(repo / "tests"),
                        "-q", "-ra", "--tb=short", "-o", f"cache_dir={work / 'cache'}",
                        "--basetemp", str(work / "pytest")],
                       cwd=work, check=True)


if __name__ == "__main__":
    main()
