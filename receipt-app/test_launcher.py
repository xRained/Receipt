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
            process=Mock(pid=456)
            with patch.object(launcher,'ROOT',root),patch('version.version',return_value='same'),\
                 patch.object(launcher,'health',side_effect=[current,started]),\
                 patch.object(launcher,'port_in_use',return_value=False),\
                 patch.object(launcher.os,'kill') as kill,patch.object(launcher.subprocess,'Popen',return_value=process),\
                 patch.object(launcher.webbrowser,'open') as browser:
                launcher.main()
                kill.assert_called_once_with(123,signal.SIGTERM)
                browser.assert_called_once_with(launcher.URL)

    def test_other_workspace_or_unknown_listener_is_not_killed(self):
        for current in [dict(app='tally-local',workspace='another-workspace',pid=123),None]:
            with patch.object(launcher,'health',return_value=current),patch.object(launcher,'port_in_use',return_value=True),\
                 patch.object(launcher.os,'kill') as kill,patch.object(launcher.subprocess,'Popen') as start:
                with self.assertRaises(RuntimeError):launcher.main()
                kill.assert_not_called();start.assert_not_called()
