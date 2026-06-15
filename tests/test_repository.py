import os
import tempfile
from collections.abc import Generator

import git
import pytest

from src.models.db_models import RepositoryConfig
from src.repository.manager import RepositoryManager


@pytest.fixture(name="manager")
def manager_fixture() -> RepositoryManager:
    return RepositoryManager()


@pytest.fixture(name="temp_dir")
def temp_dir_fixture() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_get_repo_not_found(manager: RepositoryManager) -> None:
    with pytest.raises(FileNotFoundError):
        manager.get_repo("non_existent_directory_12345")


def test_get_repo_invalid(manager: RepositoryManager, temp_dir: str) -> None:
    with pytest.raises(git.exc.InvalidGitRepositoryError):
        manager.get_repo(temp_dir)


def test_clone_invalid_existing_path(manager: RepositoryManager, temp_dir: str) -> None:
    dummy_file = os.path.join(temp_dir, "dummy.txt")
    with open(dummy_file, "w") as f:
        f.write("test")

    with pytest.raises(FileExistsError):
        manager.clone("https://github.com/example/repo.git", temp_dir)


def test_git_operations_flow(manager: RepositoryManager, temp_dir: str) -> None:
    bare_path = os.path.join(temp_dir, "bare.git")
    local_path_1 = os.path.join(temp_dir, "local_1")
    local_path_2 = os.path.join(temp_dir, "local_2")

    bare_repo = git.Repo.init(bare_path, bare=True)
    repo_1 = None
    repo_2 = None
    try:
        assert bare_repo.bare

        repo_1 = manager.clone(bare_path, local_path_1)
        assert os.path.exists(os.path.join(local_path_1, ".git"))

        repo_1.config_writer().set_value("user", "name", "Test").release()
        repo_1.config_writer().set_value("user", "email", "test@test.com").release()

        test_file = os.path.join(local_path_1, "file.txt")
        with open(test_file, "w") as f:
            f.write("hello")

        status_dirty = manager.get_status(local_path_1)
        assert status_dirty["is_dirty"] is True
        assert "file.txt" in status_dirty["untracked_files"]

        commit_hash = manager.commit_changes(
            local_path_1, "Initial commit", "Tester", "tester@test.com"
        )
        assert commit_hash != ""

        status_clean = manager.get_status(local_path_1)
        assert status_clean["is_dirty"] is False
        assert status_clean["current_commit"] == commit_hash

        manager.push(local_path_1, remote_name="origin", branch_name="master")

        repo_2 = manager.clone(bare_path, local_path_2, branch="master")
        assert os.path.exists(os.path.join(local_path_2, "file.txt"))

        repo_2.config_writer().set_value("user", "name", "Test").release()
        repo_2.config_writer().set_value("user", "email", "test@test.com").release()

        manager.checkout_branch(local_path_2, "feature-branch", create=True)
        status_branch = manager.get_status(local_path_2)
        assert status_branch["active_branch"] == "feature-branch"

        with open(os.path.join(local_path_1, "file2.txt"), "w") as f:
            f.write("world")
        manager.commit_changes(local_path_1, "Add file2")
        manager.push(local_path_1, remote_name="origin", branch_name="master")

        manager.checkout_branch(local_path_2, "master")
        manager.pull(local_path_2)
        assert os.path.exists(os.path.join(local_path_2, "file2.txt"))
    finally:
        if repo_1:
            repo_1.close()
        if repo_2:
            repo_2.close()
        bare_repo.close()


def test_sync(manager: RepositoryManager, temp_dir: str) -> None:
    bare_path = os.path.join(temp_dir, "bare.git")
    local_path = os.path.join(temp_dir, "local")

    bare_repo = git.Repo.init(bare_path, bare=True)
    repo_init = None
    repo = None
    try:
        assert bare_repo.bare

        init_local = os.path.join(temp_dir, "init_local")
        repo_init = git.Repo.init(init_local)
        repo_init.config_writer().set_value("user", "name", "Test").release()
        repo_init.config_writer().set_value("user", "email", "test@test.com").release()

        with open(os.path.join(init_local, "readme.md"), "w") as f:
            f.write("init")
        repo_init.git.add(A=True)
        repo_init.index.commit("Initial")
        repo_init.create_remote("origin", bare_path)
        repo_init.git.push("origin", "master")

        config = RepositoryConfig(
            url=bare_path,
            local_path=local_path,
            branch="master",
        )

        repo = manager.sync(config)
        assert os.path.exists(os.path.join(local_path, "readme.md"))
        assert repo.active_branch.name == "master"
    finally:
        if repo_init:
            repo_init.close()
        if repo:
            repo.close()
        bare_repo.close()
