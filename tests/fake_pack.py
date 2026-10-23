"""
A one-module domain pack for tests: real subprocesses, no chemistry.

``toy.opt_driver`` mirrors the fixture catalog's ``toy_opt`` flags. It
copies its input to ``<jobname>_optimized.xyz``, refuses a negative
charge (exit 3), and with charge 99 sleeps for a minute, which gives
tests a job they can cancel, abandon or time out.
"""

from pathlib import Path

WATER_XYZ = "3\nwater\nO 0 0 0\nH 0.76 0.59 0\nH -0.76 0.59 0\n"
SLOW_CHARGE = 99
FAKE_DRIVER = """
import argparse, json, sys, time
parser = argparse.ArgumentParser()
parser.add_argument("-i", dest="input")
parser.add_argument("-JOBNAME", dest="jobname")
parser.add_argument("-parallel", dest="parallel", type=int)
parser.add_argument("-charge", dest="charge", type=int, default=0)
parser.add_argument("-temp", dest="temp", type=float, default=300.0)
parser.add_argument("-gfnff", dest="gfnff", action="store_true")
parser.add_argument("-nokeep", dest="keep", action="store_false")
parser.add_argument("-optlevel", dest="optlevel", default="normal")
parser.add_argument("-gfn", dest="gfn", type=int, default=2)
parser.add_argument("-solvent", dest="solvent")
options = parser.parse_args()
if options.charge == 99:
    time.sleep(60)
if options.charge < 0:
    print("negative charge refused", file=sys.stderr)
    sys.exit(3)
with open(f"{options.jobname}_optimized.xyz", "w") as out:
    out.write(open(options.input).read())
with open("received.json", "w") as out:
    json.dump(vars(options), out)
"""


def install_fake_pack(root: Path) -> Path:
    """
    Write the fake pack under ``root/pack``.

    :param root: Directory to install into.
    :type root: Path
    :return: The pack's source directory (goes on PYTHONPATH).
    :rtype: Path
    """
    package = root / "pack" / "toy"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "opt_driver.py").write_text(FAKE_DRIVER)
    return root / "pack"


def create_session(artifacts_dir: Path) -> Path:
    """
    Create session ``user_1/session_1`` holding an uploaded water.xyz.

    :param artifacts_dir: Root of job workspaces.
    :type artifacts_dir: Path
    :return: The session folder.
    :rtype: Path
    """
    session = artifacts_dir / "user_1" / "session_1"
    session.mkdir(parents=True)
    (session / "water.xyz").write_text(WATER_XYZ)
    return session
