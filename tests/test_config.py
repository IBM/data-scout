"""SearchConfig path resolution and settings wiring."""
from pathlib import Path

from src.config import SearchConfig


class TestPolicyPathsAreAbsolute:
    """Relative paths resolved against the CWD, so running from anywhere but the
    repo root created a stray empty cache tree and never found the real one."""

    def test_default_paths_are_absolute(self):
        config = SearchConfig(_env_file=None)

        for path in (config.allowed_path, config.not_allowed_path,
                     config.reasoning_path, config.error_log_path):
            assert Path(path).is_absolute(), f"{path} is relative"

    def test_paths_do_not_depend_on_the_working_directory(self, tmp_path, monkeypatch):
        before = SearchConfig(_env_file=None).allowed_path
        monkeypatch.chdir(tmp_path)
        after = SearchConfig(_env_file=None).allowed_path

        assert before == after

    def test_policy_dir_env_var_relocates_every_file(self, monkeypatch):
        monkeypatch.setenv("POLICY_DIR", "/tmp/ds-policy-override")
        config = SearchConfig(_env_file=None)

        assert config.allowed_path == Path("/tmp/ds-policy-override/allowed.txt")
        assert config.reasoning_path == Path("/tmp/ds-policy-override/reasoning.jsonl")


class TestSettingsWiring:
    def test_settings_config_dict_is_used(self):
        """ConfigDict is not the settings type and silently ignored settings-only
        keys such as an env_file typo."""
        assert isinstance(SearchConfig.model_config, dict)
        assert SearchConfig.model_config.get("env_file") == ".env"
