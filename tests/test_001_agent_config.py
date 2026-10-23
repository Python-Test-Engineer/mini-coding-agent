"""Verify project configuration is loaded from .env safely."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agent


class EnvironmentConfigTests(unittest.TestCase):
    def test_001_loads_credentials_and_model_from_project_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=dotenv-test-key\nMODEL=dotenv-test-model\n",
                encoding="utf-8",
            )
            with patch.object(agent, "ROOT_DIR", root), patch.dict(
                os.environ, {}, clear=True
            ):
                agent._load_dotenv()

                self.assertEqual(agent._api_key(), "dotenv-test-key")
                self.assertEqual(agent._model(), "dotenv-test-model")

    def test_002_environment_variables_override_project_env_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".env").write_text(
                "OPENROUTER_API_KEY=dotenv-test-key\nMODEL=dotenv-test-model\n",
                encoding="utf-8",
            )
            with patch.object(agent, "ROOT_DIR", root), patch.dict(
                os.environ,
                {
                    "OPENROUTER_API_KEY": "environment-test-key",
                    "MODEL": "environment-test-model",
                },
                clear=True,
            ):
                agent._load_dotenv()

                self.assertEqual(agent._api_key(), "environment-test-key")
                self.assertEqual(agent._model(), "environment-test-model")


if __name__ == "__main__":
    unittest.main()
