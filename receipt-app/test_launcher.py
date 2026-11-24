import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
import launcher
import signal


class LauncherTests(unittest.TestCase):
    def test_start_restarts_same_version_without_trusting_copied_pid_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'data').mkdir();(root/'data/server.pid').write_text('99999')
            current=dict(app='tally-local',workspace=str(root),pid=123,version='same')
            started=dict(current,pid=456)
            with patch.object(launcher,'ROOT',root),\
                 patch.object(launcher,'health',side_effect=[current,started]),\
                 patch.object(launcher,'port_in_use',return_value=False),\
                 patch.object(launcher.os,'kill') as kill,patch.object(launcher,'launch_foreground') as launch:
                launcher.main()
                kill.assert_called_once_with(123,signal.SIGTERM)
                launch.assert_called_once()

    def test_other_workspace_or_unknown_listener_is_not_killed(self):
        for current in [dict(app='tally-local',workspace='another-workspace',pid=123),None]:
            with patch.object(launcher,'health',return_value=current),patch.object(launcher,'port_in_use',return_value=True),\
                 patch.object(launcher.os,'kill') as kill,patch.object(launcher,'launch_foreground') as start:
                with self.assertRaises(RuntimeError):launcher.main()
                kill.assert_not_called();start.assert_not_called()

    def test_server_runs_in_console_process_and_ctrl_c_returns(self):
        with patch.object(launcher.threading,'Thread') as thread,patch.object(launcher.runpy,'run_path',side_effect=KeyboardInterrupt) as run:
            launcher.launch_foreground()
            self.assertTrue(thread.call_args.kwargs['daemon'])
            run.assert_called_once_with(str(launcher.ROOT/'app.py'),run_name='__main__')

    def test_browser_opens_only_for_this_server_process(self):
        current=dict(app='tally-local',workspace=str(launcher.ROOT),pid=launcher.os.getpid())
        with patch.object(launcher,'health',return_value=current),patch.object(launcher.webbrowser,'open') as browser:
            launcher.open_when_ready()
            browser.assert_called_once_with(launcher.URL)
