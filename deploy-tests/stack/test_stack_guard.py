import guard


def test_stack_project_and_folder_are_throwaway(deploy_stack):
    project, folder = deploy_stack
    assert project.startswith("aio-deploy-")
    assert not folder.resolve().is_relative_to(guard.PRODUCTION_HOME)
