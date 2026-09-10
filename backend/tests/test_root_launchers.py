import argparse
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_root_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run_backend = load_root_module("root_run_backend", "run_backend.py")
run_frontend = load_root_module("root_run_frontend", "run_frontend.py")


class RootLauncherTests(unittest.TestCase):
    def test_backend_launcher_uses_current_app_and_scoped_reload(self):
        args = argparse.Namespace(host="127.0.0.1", port=8010, no_reload=False)
        with (
            patch.object(run_backend, "parse_args", return_value=args),
            patch.object(run_backend.os, "chdir"),
            patch.object(run_backend.sys, "path"),
            patch.object(run_backend.uvicorn, "run") as uvicorn_run,
        ):
            run_backend.main()

        kwargs = uvicorn_run.call_args.kwargs
        self.assertEqual(uvicorn_run.call_args.args[0], "app.main:app")
        self.assertEqual(kwargs["port"], 8010)
        self.assertEqual(kwargs["reload_dirs"], [str(run_backend.APP_ROOT)])

    def test_frontend_launcher_syncs_proxy_and_requires_requested_port(self):
        args = argparse.Namespace(
            host="127.0.0.1",
            port=3010,
            backend_url="http://127.0.0.1:8010/",
        )
        with (
            patch.object(run_frontend, "parse_args", return_value=args),
            patch.object(run_frontend.shutil, "which", return_value="npm.cmd"),
            patch.object(run_frontend.subprocess, "call", return_value=0) as call,
        ):
            result = run_frontend.main()

        command = call.call_args.args[0]
        env = call.call_args.kwargs["env"]
        self.assertEqual(result, 0)
        self.assertIn("--strictPort", command)
        self.assertEqual(env["VITE_BACKEND_URL"], "http://127.0.0.1:8010")
        self.assertEqual(call.call_args.kwargs["cwd"], run_frontend.FRONTEND_ROOT)
        self.assertNotEqual(env, os.environ)

    def test_backend_launcher_refuses_remote_bind_without_token(self):
        args = argparse.Namespace(host="0.0.0.0", port=8010, no_reload=True)
        with (
            patch.object(run_backend, "parse_args", return_value=args),
            patch.object(run_backend.os, "chdir"),
            patch.object(run_backend.sys, "path"),
            patch("app.core.config.settings.api_token", ""),
            self.assertRaises(SystemExit),
        ):
            run_backend.main()


if __name__ == "__main__":
    unittest.main()
