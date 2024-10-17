import signal
from unittest import mock

import pytest

from flow_initiator.spawner.elements.process_element import ProcessElement


@pytest.fixture
def mock_subprocess():
    """Fixture to mock subprocess creation."""
    with mock.patch(
        "flow_initiator.spawner.elements.process_element.asyncio.create_subprocess_exec"
    ) as mock_proc:
        proc_mock = mock.Mock()
        proc_mock.returncode = None  # Process is still running
        mock_proc.return_value = proc_mock
        yield mock_proc


@pytest.fixture
def process_element():
    """Create a ProcessElement instance."""
    return ProcessElement(
        command=["ls"], cwd="/tmp", stdout=mock.Mock(), logger=mock.Mock()
    )


@pytest.mark.asyncio
async def test_ensure_process_kill_sends_sigint(process_element):
    """Test SIGINT is sent when process does not terminate within timeout_term."""
    process_element.proc = mock.Mock()
    process_element.proc.returncode = None  # Process still running
    process_element.proc.pid = 12345

    with mock.patch("time.time", side_effect=[0, 2, 4, 6]):
        with mock.patch(
            "flow_initiator.spawner.elements.process_element.psutil.pid_exists",
            side_effect=[True, True, False],
        ):
            await process_element.ensure_process_kill()

    process_element.proc.send_signal.assert_called_with(signal.SIGINT)
    process_element._logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_process_kill_sends_sigkill_after_sigint(process_element):
    """Test SIGKILL is sent when process does not terminate after SIGINT."""
    process_element.proc = mock.Mock()
    process_element.proc.returncode = None  # Process still running
    process_element.proc.pid = 12345

    with mock.patch("time.time", side_effect=[0, 2, 4, 8, 10, 12]):
        with mock.patch(
            "flow_initiator.spawner.elements.process_element.psutil.pid_exists",
            side_effect=[True, True, True, True, False],
        ):
            await process_element.ensure_process_kill()

    process_element.proc.send_signal.assert_any_call(
        signal.SIGINT
    )  # First, send SIGINT
    process_element.proc.send_signal.assert_any_call(
        signal.SIGKILL
    )  # Then, send SIGKILL
    process_element._logger.error.assert_called()


@pytest.mark.asyncio
async def test_process_terminates_before_signals(process_element):
    """Test process terminates normally before signals are sent."""
    process_element.proc = mock.Mock()
    process_element.proc.returncode = 0  # Process terminated successfully
    process_element.proc.pid = 12345

    with mock.patch(
        "flow_initiator.spawner.elements.process_element.psutil.pid_exists",
        side_effect=True,
    ):
        return_code = await process_element.ensure_process_kill()

    assert return_code == 0
    process_element.proc.send_signal.assert_not_called()
    process_element._logger.debug.assert_called()
