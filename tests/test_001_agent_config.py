"""Verify project configuration is loaded from .env safely."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import brain


class EnvironmentConfigTests(unittest.TestCase):
    def test_001_loads_credentials_and_model_from_project_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=dotenv-test-key\nMODEL=dotenv-test-model\n",
                encoding="utf-8",
            )
            # Model settings live in brain.py, so its repository root is what
            # decides which .env file is read.
            with patch.object(brain, "ROOT_DIR", root), patch.dict(
                os.environ, {}, clear=True
            ):
                brain.load_env()

                self.assertEqual(brain.api_key(), "dotenv-test-key")
                self.assertEqual(brain.model_name(), "dotenv-test-model")

    def test_002_environment_variables_override_project_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=dotenv-test-key\nMODEL=dotenv-test-model\n",
                encoding="utf-8",
            )
            with patch.object(brain, "ROOT_DIR", root), patch.dict(
                os.environ,
                {
                    "OPENROUTER_API_KEY": "environment-test-key",
                    "MODEL": "environment-test-model",
                },
                clear=True,
            ):
                brain.load_env()

                self.assertEqual(brain.api_key(), "environment-test-key")
                self.assertEqual(brain.model_name(), "environment-test-model")


if __name__ == "__main__":
    unittest.main()
