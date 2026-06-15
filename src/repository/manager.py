import os
from typing import Any

import git

from src.models.db_models import RepositoryConfig


class RepositoryManager:
    def get_repo(self, local_path: str) -> git.Repo:
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Path '{local_path}' does not exist.")
        return git.Repo(local_path)

    def clone(self, url: str, local_path: str, branch: str | None = None) -> git.Repo:
        if os.path.exists(local_path):
            if os.path.exists(os.path.join(local_path, ".git")):
                repo = self.get_repo(local_path)
                if branch:
                    try:
                        self.checkout_branch(local_path, branch)
                    finally:
                        repo.close()
                return self.get_repo(local_path)
            else:
                raise FileExistsError(
                    f"Path '{local_path}' exists but is not a valid Git repository."
                )

        if branch:
            return git.Repo.clone_from(url, local_path, branch=branch)
        return git.Repo.clone_from(url, local_path)

    def sync(self, config: RepositoryConfig) -> git.Repo:
        repo = self.clone(config.url, config.local_path, config.branch)
        try:
            self.pull(config.local_path)
        finally:
            repo.close()
        return self.get_repo(config.local_path)

    def checkout_branch(
        self, local_path: str, branch_name: str, create: bool = False
    ) -> None:
        repo = self.get_repo(local_path)
        try:
            if create:
                if branch_name in repo.heads:
                    repo.git.checkout(branch_name)
                else:
                    repo.git.checkout("-b", branch_name)
            else:
                repo.git.checkout(branch_name)
        except git.exc.GitCommandError as e:
            raise RuntimeError(f"Failed to checkout branch '{branch_name}': {e}") from e
        finally:
            repo.close()

    def pull(self, local_path: str) -> None:
        repo = self.get_repo(local_path)
        try:
            if not repo.remotes:
                return

            try:
                origin = repo.remotes.origin
                origin.pull()
            except git.exc.GitCommandError as e:
                raise RuntimeError(f"Failed to pull changes: {e}") from e
        finally:
            repo.close()

    def commit_changes(
        self,
        local_path: str,
        message: str,
        author_name: str | None = None,
        author_email: str | None = None,
    ) -> str:
        repo = self.get_repo(local_path)
        try:
            repo.git.add(A=True)

            if not repo.is_dirty() and not repo.untracked_files:
                return str(repo.head.commit.hexsha)

            actor = None
            if author_name and author_email:
                actor = git.Actor(author_name, author_email)

            commit = repo.index.commit(message, author=actor)
            return str(commit.hexsha)
        except git.exc.GitCommandError as e:
            raise RuntimeError(f"Failed to commit changes: {e}") from e
        finally:
            repo.close()

    def push(
        self,
        local_path: str,
        remote_name: str = "origin",
        branch_name: str | None = None,
    ) -> None:
        repo = self.get_repo(local_path)
        try:
            if not repo.remotes:
                raise RuntimeError("No remotes configured for this repository.")

            try:
                remote = repo.remote(name=remote_name)
                target_branch = branch_name or str(repo.active_branch.name)
                remote.push(refspec=f"{target_branch}:{target_branch}")
            except git.exc.GitCommandError as e:
                raise RuntimeError(
                    f"Failed to push changes to remote '{remote_name}': {e}"
                ) from e
        finally:
            repo.close()

    def get_status(self, local_path: str) -> dict[str, Any]:
        repo = self.get_repo(local_path)
        try:
            modified_files = []
            try:
                for diff in repo.index.diff(None):
                    if diff.a_path and diff.a_path not in modified_files:
                        modified_files.append(diff.a_path)
                if repo.head.is_valid():
                    for diff in repo.index.diff("HEAD"):
                        if diff.a_path and diff.a_path not in modified_files:
                            modified_files.append(diff.a_path)
            except Exception:
                pass

            active_branch = ""
            try:
                active_branch = str(repo.active_branch.name)
            except TypeError:
                active_branch = "DETACHED"

            current_commit = ""
            if repo.head.is_valid():
                try:
                    current_commit = str(repo.head.commit.hexsha)
                except (ValueError, AttributeError):
                    current_commit = ""

            return {
                "is_dirty": repo.is_dirty(untracked_files=True),
                "active_branch": active_branch,
                "current_commit": current_commit,
                "untracked_files": repo.untracked_files,
                "modified_files": modified_files,
            }
        finally:
            repo.close()
