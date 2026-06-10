from .machine_tools import (
    apply_patch,
    git_branch,
    git_commit,
    list_dir,
    read_file,
    retrieve,
    run_build,
    run_lint,
    run_tests,
    search_code,
)
from .orchestrator_tools import comment, git_push, open_pr

MACHINE_TOOLS = [
    read_file,
    list_dir,
    search_code,
    retrieve,
    apply_patch,
    run_tests,
    run_lint,
    run_build,
    git_branch,
    git_commit,
]

ORCHESTRATOR_TOOLS = [git_push, open_pr, comment]


def all_tools():
    return MACHINE_TOOLS + ORCHESTRATOR_TOOLS
