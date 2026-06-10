from pydantic import BaseModel, Field


class ReadFileInput(BaseModel):
    path: str = Field(description="Absolute path to the file on the machine")


class ListDirInput(BaseModel):
    path: str = Field(description="Absolute path to the directory on the machine")


class SearchCodeInput(BaseModel):
    query: str = Field(description="Search pattern (ripgrep regex)")


class RetrieveInput(BaseModel):
    query: str = Field(description="Natural language query for semantic code search")


class ApplyPatchInput(BaseModel):
    unified_diff: str = Field(
        description="A unified diff (output of git diff) to apply with git apply"
    )


class RunTestsInput(BaseModel):
    pass


class RunLintInput(BaseModel):
    pass


class RunBuildInput(BaseModel):
    pass


class GitBranchInput(BaseModel):
    name: str = Field(description="Branch name to create and checkout")


class GitCommitInput(BaseModel):
    message: str = Field(description="Commit message")


class GitPushInput(BaseModel):
    branch_name: str = Field(description="Branch to push to origin")


class OpenPrInput(BaseModel):
    repo_full_name: str
    head_branch: str
    base_branch: str
    title: str
    body: str
    draft: bool = False


class CommentInput(BaseModel):
    repo_full_name: str
    issue_or_pr_number: int
    body: str
