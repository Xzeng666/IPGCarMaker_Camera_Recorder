import unittest

from carmaker_gui.control_state import control_policy


class ControlPolicyTests(unittest.TestCase):
    def test_stopped(self):
        policy = control_policy(worker_active=False, stop_requested=False, connection_test_active=False)
        self.assertTrue(policy.start_enabled)
        self.assertFalse(policy.stop_enabled)
        self.assertTrue(policy.settings_enabled)
        self.assertTrue(policy.connection_test_enabled)
        self.assertTrue(policy.save_shortcut_enabled)

    def test_running_stop_is_available(self):
        policy = control_policy(worker_active=True, stop_requested=False, connection_test_active=False)
        self.assertFalse(policy.start_enabled)
        self.assertTrue(policy.stop_enabled)
        self.assertFalse(policy.settings_enabled)
        self.assertFalse(policy.connection_test_enabled)
        self.assertFalse(policy.save_shortcut_enabled)

    def test_stopping_prevents_double_stop(self):
        policy = control_policy(worker_active=True, stop_requested=True, connection_test_active=False)
        self.assertFalse(policy.start_enabled)
        self.assertFalse(policy.stop_enabled)

    def test_connection_test_blocks_start(self):
        policy = control_policy(worker_active=False, stop_requested=False, connection_test_active=True)
        self.assertFalse(policy.start_enabled)
        self.assertFalse(policy.connection_test_enabled)
        self.assertTrue(policy.settings_enabled)


if __name__ == "__main__":
    unittest.main()
