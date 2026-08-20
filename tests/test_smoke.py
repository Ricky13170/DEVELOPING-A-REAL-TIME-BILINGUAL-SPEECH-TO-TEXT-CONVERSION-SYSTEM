"""Fast architecture/configuration checks; never download model weights."""

import ast
import unittest
import subprocess
import sys
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def imported_modules(path: Path) -> set[str]:
    """Return static imports without importing the module under test."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


class ProjectSmokeTests(unittest.TestCase):
    def test_main_is_the_only_runtime_entrypoint(self):
        self.assertTrue((PROJECT_ROOT / "main.py").is_file())
        self.assertFalse((PROJECT_ROOT / "local_server.py").exists())
        self.assertNotIn("modal", imported_modules(PROJECT_ROOT / "main.py"))

    def test_lockfile_matches_lightweight_runtime(self):
        """Keep removed training/heavy pipeline packages out of the lockfile."""

        with (PROJECT_ROOT / "uv.lock").open("rb") as file:
            lockfile = tomllib.load(file)

        self.assertEqual(lockfile["requires-python"], "==3.11.*")
        package_names = {
            package["name"]
            for package in lockfile.get("package", [])
        }
        removed_stack = {
            "modal",
            "peft",
            "pyannote-audio",
            "torchaudio",
            "torchvision",
            "whisperx",
        }
        self.assertTrue(
            package_names.isdisjoint(removed_stack),
            f"Removed packages returned: {package_names & removed_stack}",
        )

    def test_requirements_match_pyproject(self):
        """Prevent Docker requirements from drifting from the uv project."""

        with (PROJECT_ROOT / "pyproject.toml").open("rb") as file:
            project_dependencies = tomllib.load(file)["project"]["dependencies"]

        requirements = [
            line.strip()
            for line in (PROJECT_ROOT / "requirements.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(project_dependencies, requirements)

    def test_feature_dependency_boundaries(self):
        """Keep low-level features independent from orchestration and web."""

        speech_files = (PROJECT_ROOT / "backend" / "speech").glob("*.py")
        for path in speech_files:
            imports = imported_modules(path)
            self.assertFalse(
                any(
                    module == "backend.web_app"
                    or module.startswith("backend.realtime")
                    for module in imports
                ),
                f"{path.name} crosses the speech feature boundary",
            )

        web_imports = imported_modules(PROJECT_ROOT / "backend" / "web_app.py")
        self.assertNotIn("backend.realtime.session", web_imports)

        webrtc_imports = imported_modules(
            PROJECT_ROOT / "backend" / "realtime" / "webrtc.py"
        )
        self.assertNotIn("backend.realtime.session", webrtc_imports)

    def test_web_import_does_not_eager_load_model_stack(self):
        code = """
import sys
import backend.web_app
blocked = [
    name for name in ('torch', 'transformers', 'faster_whisper')
    if name in sys.modules
]
print('MODEL_IMPORTS=' + ','.join(blocked))
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            result.stdout.strip().splitlines()[-1],
            "MODEL_IMPORTS=",
        )

    def test_main_entrypoint_applies_config_before_session_import(self):
        code = """
from types import SimpleNamespace
import main
cfg = main.apply_config(
    SimpleNamespace(whisper_model='base', enable_groq=False)
)
from backend.realtime import session
print(
    cfg.ASR_DEVICE,
    cfg.ASR_COMPUTE_TYPE,
    cfg.TRANSLATION_DEVICE,
    session.WHISPER_MODEL,
)
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout.strip().splitlines()[-1], "cpu int8 cpu base")

    def test_feature_packages_import_without_loading_models(self):
        from backend.realtime.session import ASRService
        from backend.speech.asr import WhisperASR

        self.assertIsNotNone(ASRService)
        self.assertIsNotNone(WhisperASR)

    def test_translation_direction_mapping_without_model_download(self):
        from backend.translation import MarianTranslator

        translator = MarianTranslator()
        self.assertEqual(
            translator._direction("vie_Latn", "eng_Latn"),
            ("vi", "en"),
        )
        self.assertEqual(
            translator.translate("Keep this text", "en", "en"),
            "Keep this text",
        )
        self.assertFalse(translator.is_loaded)


if __name__ == "__main__":
    unittest.main()
