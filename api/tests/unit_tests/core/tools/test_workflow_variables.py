"""
Tests for workflow variables functionality in plugins
"""
import pytest
from unittest.mock import Mock, patch


def test_plugin_tool_manager_workflow_variables_injection():
    """Test that PluginToolManager correctly injects workflow variables"""
    from core.plugin.impl.tool import PluginToolManager

    manager = PluginToolManager()

    # Mock variable pool
    mock_variable_pool = Mock()
    mock_variable_pool.user_inputs = {"user_name": "John Doe"}

    system_var = Mock()
    system_var.to_dict.return_value = {"app_id": "test_app", "user_id": "test_user"}
    mock_variable_pool.system_variables = system_var

    env_var = Mock()
    env_var.name = "API_KEY"
    env_var.get_value.return_value = "test_key"
    mock_variable_pool.environment_variables = [env_var]

    # Test injection
    original_credentials = {"api_key": "original_key"}
    enhanced_credentials = manager._inject_workflow_variables_to_credentials(
        original_credentials, mock_variable_pool
    )

    # Verify original credentials preserved
    assert enhanced_credentials["api_key"] == "original_key"

    # Verify workflow variables injected
    assert "__workflow_variables__" in enhanced_credentials
    workflow_vars = enhanced_credentials["__workflow_variables__"]

    assert workflow_vars["user_inputs"]["user_name"] == "John Doe"
    assert workflow_vars["system_variables"]["app_id"] == "test_app"
    assert workflow_vars["environment_variables"]["API_KEY"] == "test_key"


def test_plugin_tool_manager_serialize_user_inputs():
    """Test user inputs serialization"""
    from core.plugin.impl.tool import PluginToolManager

    manager = PluginToolManager()

    mock_variable_pool = Mock()
    mock_variable_pool.user_inputs = {
        "name": "Test",
        "age": 25,
        "active": True
    }

    result = manager._serialize_user_inputs(mock_variable_pool)

    assert result == {
        "name": "Test",
        "age": 25,
        "active": True
    }


def test_plugin_tool_manager_serialize_system_variables():
    """Test system variables serialization"""
    from core.plugin.impl.tool import PluginToolManager

    manager = PluginToolManager()

    mock_variable_pool = Mock()
    system_var = Mock()
    system_var.to_dict.return_value = {
        "app_id": "test_app",
        "user_id": "test_user",
        "workflow_id": "test_workflow"
    }
    mock_variable_pool.system_variables = system_var

    result = manager._serialize_system_variables(mock_variable_pool)

    assert result == {
        "app_id": "test_app",
        "user_id": "test_user",
        "workflow_id": "test_workflow"
    }


def test_plugin_tool_manager_serialize_environment_variables():
    """Test environment variables serialization"""
    from core.plugin.impl.tool import PluginToolManager

    manager = PluginToolManager()

    mock_variable_pool = Mock()

    env_var1 = Mock()
    env_var1.name = "ENV1"
    env_var1.get_value.return_value = "value1"

    env_var2 = Mock()
    env_var2.name = "ENV2"
    env_var2.get_value.return_value = "value2"

    mock_variable_pool.environment_variables = [env_var1, env_var2]

    result = manager._serialize_environment_variables(mock_variable_pool)

    assert result == {
        "ENV1": "value1",
        "ENV2": "value2"
    }


def test_plugin_tool_manager_no_variable_pool():
    """Test behavior when variable_pool is None"""
    from core.plugin.impl.tool import PluginToolManager

    manager = PluginToolManager()

    original_credentials = {"api_key": "test_key"}
    enhanced_credentials = manager._inject_workflow_variables_to_credentials(
        original_credentials, None
    )

    # Should return original credentials unchanged
    assert enhanced_credentials == original_credentials
    assert "__workflow_variables__" not in enhanced_credentials