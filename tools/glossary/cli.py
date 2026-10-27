import argparse
import os
import subprocess
import sys


TOOLS = {
    "sync": "sync_project_glossary.py",
    "fill": "fill_glossary_missing.py",
    "check": "check_glossary_consistency.py",
    "apply": "apply_glossary_conflicts.py",
    "inspect": "inspect_glossary_xlsx.py",
}


def run_tool(tool_name, args):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.join(script_dir, TOOLS[tool_name])
    cmd = [sys.executable, script] + args
    return subprocess.call(cmd)


def main():
    parser = argparse.ArgumentParser(
        description="Glossary tools unified entrypoint",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "tool",
        choices=sorted(TOOLS.keys()),
        help=(
            "Tool to run:\n"
            "  sync    Sync workbook into project glossary JSON files\n"
            "  fill    Fill missing translations in workbook\n"
            "  check   Check glossary consistency conflicts\n"
            "  apply   Apply reviewed conflict CSV back to workbook\n"
            "  inspect Inspect workbook sheet/header structure"
        ),
    )
    parser.add_argument("tool_args", nargs=argparse.REMAINDER, help="Arguments passed to the selected tool")

    ns = parser.parse_args()
    rc = run_tool(ns.tool, ns.tool_args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
