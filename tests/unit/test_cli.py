"""Unit tests for CLI commands (init, status, reset)."""

import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from localostack.cli.main import cli


class TestInit:
    def test_creates_clouds_yaml(self, tmp_path):
        clouds_dir = tmp_path / ".config" / "openstack"
        clouds_file = clouds_dir / "clouds.yaml"

        with patch.object(Path, "home", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 0
        assert clouds_file.exists()
        content = clouds_file.read_text()
        assert "localostack" in content
        assert "auth_url" in content
        assert "http://localhost:5000/v3" in content

    def test_refuses_overwrite_without_force(self, tmp_path):
        clouds_dir = tmp_path / ".config" / "openstack"
        clouds_dir.mkdir(parents=True)
        clouds_file = clouds_dir / "clouds.yaml"
        clouds_file.write_text("existing content")

        with patch.object(Path, "home", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["init"])

        assert result.exit_code == 1
        assert "already exists" in result.output
        assert clouds_file.read_text() == "existing content"

    def test_overwrites_with_force(self, tmp_path):
        clouds_dir = tmp_path / ".config" / "openstack"
        clouds_dir.mkdir(parents=True)
        clouds_file = clouds_dir / "clouds.yaml"
        clouds_file.write_text("old content")

        with patch.object(Path, "home", return_value=tmp_path):
            runner = CliRunner()
            result = runner.invoke(cli, ["init", "--force"])

        assert result.exit_code == 0
        assert "localostack" in clouds_file.read_text()


class TestStatus:
    def test_not_running(self):
        runner = CliRunner()
        with patch.dict(os.environ, {
            "LOCALOSTACK_KEYSTONE_PORT": "59999",
            "LOCALOSTACK_NOVA_PORT": "59998",
            "LOCALOSTACK_NEUTRON_PORT": "59997",
            "LOCALOSTACK_GLANCE_PORT": "59996",
            "LOCALOSTACK_CINDER_PORT": "59995",
            "LOCALOSTACK_PLACEMENT_PORT": "59994",
            "LOCALOSTACK_HEAT_PORT": "59993",
            "LOCALOSTACK_SWIFT_PORT": "59992",
            "LOCALOSTACK_BARBICAN_PORT": "59991",
            "LOCALOSTACK_OCTAVIA_PORT": "59990",
            "LOCALOSTACK_ADMIN_PORT": "59989",
        }):
            result = runner.invoke(cli, ["status"])
        assert result.exit_code == 1
        assert "not running" in result.output


class TestReset:
    def test_not_running(self):
        runner = CliRunner()
        with patch.dict(os.environ, {"LOCALOSTACK_ADMIN_PORT": "59999"}):
            result = runner.invoke(cli, ["reset"])
        assert result.exit_code == 1
        assert "not running" in result.output
