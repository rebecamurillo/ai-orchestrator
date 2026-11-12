import pytest

import harness

pytestmark = pytest.mark.stack


def test_release_n_installs_answers_healthz_and_tears_down(installed_stack, release_n):
    stack = installed_stack(release_n)
    assert stack.install().returncode == 0
    harness.wait_for_healthz(stack.client())
    assert stack.client().healthz().status_code == harness.HTTP_OK
    stack.teardown()
    assert stack.containers() == []
