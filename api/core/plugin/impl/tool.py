from collections.abc import Generator
from typing import Any

from pydantic import BaseModel

from core.plugin.entities.plugin_daemon import (
    PluginBasicBooleanResponse,
    PluginToolProviderEntity,
)
from core.plugin.impl.base import BasePluginClient
from core.plugin.utils.chunk_merger import merge_blob_chunks
from core.schemas.resolver import resolve_dify_schema_refs
from core.tools.entities.tool_entities import CredentialType, ToolInvokeMessage, ToolParameter
from models.provider_ids import GenericProviderID, ToolProviderID


class PluginToolManager(BasePluginClient):
    def fetch_tool_providers(self, tenant_id: str) -> list[PluginToolProviderEntity]:
        """
        Fetch tool providers for the given tenant.
        """

        def transformer(json_response: dict[str, Any]):
            for provider in json_response.get("data", []):
                declaration = provider.get("declaration", {}) or {}
                provider_name = declaration.get("identity", {}).get("name")
                for tool in declaration.get("tools", []):
                    tool["identity"]["provider"] = provider_name
                    # resolve refs
                    if tool.get("output_schema"):
                        tool["output_schema"] = resolve_dify_schema_refs(tool["output_schema"])

            return json_response

        response = self._request_with_plugin_daemon_response(
            "GET",
            f"plugin/{tenant_id}/management/tools",
            list[PluginToolProviderEntity],
            params={"page": 1, "page_size": 256},
            transformer=transformer,
        )

        for provider in response:
            provider.declaration.identity.name = f"{provider.plugin_id}/{provider.declaration.identity.name}"

            # override the provider name for each tool to plugin_id/provider_name
            for tool in provider.declaration.tools:
                tool.identity.provider = provider.declaration.identity.name

        return response

    def fetch_tool_provider(self, tenant_id: str, provider: str) -> PluginToolProviderEntity:
        """
        Fetch tool provider for the given tenant and plugin.
        """
        tool_provider_id = ToolProviderID(provider)

        def transformer(json_response: dict[str, Any]):
            data = json_response.get("data")
            if data:
                for tool in data.get("declaration", {}).get("tools", []):
                    tool["identity"]["provider"] = tool_provider_id.provider_name
                    # resolve refs
                    if tool.get("output_schema"):
                        tool["output_schema"] = resolve_dify_schema_refs(tool["output_schema"])

            return json_response

        response = self._request_with_plugin_daemon_response(
            "GET",
            f"plugin/{tenant_id}/management/tool",
            PluginToolProviderEntity,
            params={"provider": tool_provider_id.provider_name, "plugin_id": tool_provider_id.plugin_id},
            transformer=transformer,
        )

        response.declaration.identity.name = f"{response.plugin_id}/{response.declaration.identity.name}"

        # override the provider name for each tool to plugin_id/provider_name
        for tool in response.declaration.tools:
            tool.identity.provider = response.declaration.identity.name

        return response

    def invoke(
        self,
        tenant_id: str,
        user_id: str,
        tool_provider: str,
        tool_name: str,
        credentials: dict[str, Any],
        credential_type: CredentialType,
        tool_parameters: dict[str, Any],
        conversation_id: str | None = None,
        app_id: str | None = None,
        message_id: str | None = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the tool with the given tenant, user, plugin, provider, name, credentials and parameters.
        """

        tool_provider_id = GenericProviderID(tool_provider)

        response = self._request_with_plugin_daemon_response_stream(
            "POST",
            f"plugin/{tenant_id}/dispatch/tool/invoke",
            ToolInvokeMessage,
            data={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "app_id": app_id,
                "message_id": message_id,
                "data": {
                    "provider": tool_provider_id.provider_name,
                    "tool": tool_name,
                    "credentials": credentials,
                    "credential_type": credential_type,
                    "tool_parameters": tool_parameters,
                },
            },
            headers={
                "X-Plugin-ID": tool_provider_id.plugin_id,
                "Content-Type": "application/json",
            },
        )

        return merge_blob_chunks(response)

    def validate_provider_credentials(
        self, tenant_id: str, user_id: str, provider: str, credentials: dict[str, Any]
    ) -> bool:
        """
        validate the credentials of the provider
        """
        tool_provider_id = GenericProviderID(provider)

        response = self._request_with_plugin_daemon_response_stream(
            "POST",
            f"plugin/{tenant_id}/dispatch/tool/validate_credentials",
            PluginBasicBooleanResponse,
            data={
                "user_id": user_id,
                "data": {
                    "provider": tool_provider_id.provider_name,
                    "credentials": credentials,
                },
            },
            headers={
                "X-Plugin-ID": tool_provider_id.plugin_id,
                "Content-Type": "application/json",
            },
        )

        for resp in response:
            return resp.result

        return False

    def validate_datasource_credentials(
        self, tenant_id: str, user_id: str, provider: str, credentials: dict[str, Any]
    ) -> bool:
        """
        validate the credentials of the datasource
        """
        tool_provider_id = GenericProviderID(provider)

        response = self._request_with_plugin_daemon_response_stream(
            "POST",
            f"plugin/{tenant_id}/dispatch/datasource/validate_credentials",
            PluginBasicBooleanResponse,
            data={
                "user_id": user_id,
                "data": {
                    "provider": tool_provider_id.provider_name,
                    "credentials": credentials,
                },
            },
            headers={
                "X-Plugin-ID": tool_provider_id.plugin_id,
                "Content-Type": "application/json",
            },
        )

        for resp in response:
            return resp.result

        return False

    def get_runtime_parameters(
        self,
        tenant_id: str,
        user_id: str,
        provider: str,
        credentials: dict[str, Any],
        tool: str,
        conversation_id: str | None = None,
        app_id: str | None = None,
        message_id: str | None = None,
        variable_pool: Any = None,  # 🆕 新增：工作流变量池参数
    ) -> list[ToolParameter]:
        """
        get the runtime parameters of the tool
        """
        tool_provider_id = GenericProviderID(provider)

        # 🆕 新增：将工作流变量注入到凭证中，供插件获取
        credentials = self._inject_workflow_variables_to_credentials(credentials, variable_pool)

        class RuntimeParametersResponse(BaseModel):
            parameters: list[ToolParameter]

        response = self._request_with_plugin_daemon_response_stream(
            "POST",
            f"plugin/{tenant_id}/dispatch/tool/get_runtime_parameters",
            RuntimeParametersResponse,
            data={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "app_id": app_id,
                "message_id": message_id,
                "data": {
                    "provider": tool_provider_id.provider_name,
                    "tool": tool,
                    "credentials": credentials,  # 🆕 使用包含工作流变量的凭证
                },
            },
            headers={
                "X-Plugin-ID": tool_provider_id.plugin_id,
                "Content-Type": "application/json",
            },
        )

        for resp in response:
            return resp.parameters

        return []

    def _inject_workflow_variables_to_credentials(self, credentials: dict, variable_pool) -> dict:
        """
        将工作流变量注入到凭证中，供插件获取

        Args:
            credentials: 原始凭证
            variable_pool: 工作流变量池

        Returns:
            dict: 包含工作流变量的凭证
        """
        credentials = credentials.copy()

        if variable_pool:
            workflow_variables = {
                'user_inputs': self._serialize_user_inputs(variable_pool),
                'system_variables': self._serialize_system_variables(variable_pool),
                'environment_variables': self._serialize_environment_variables(variable_pool)
            }
            credentials['__workflow_variables__'] = workflow_variables

        return credentials

    def _serialize_user_inputs(self, variable_pool) -> dict:
        """序列化用户输入变量"""
        if hasattr(variable_pool, 'user_inputs') and variable_pool.user_inputs:
            return variable_pool.user_inputs
        return {}

    def _serialize_system_variables(self, variable_pool) -> dict:
        """序列化系统变量"""
        if not variable_pool or not variable_pool.system_variables:
            return {}

        # 系统变量是SystemVariable对象，需要转换为字典
        return variable_pool.system_variables.to_dict()

    def _serialize_environment_variables(self, variable_pool) -> dict:
        """序列化环境变量"""
        if not variable_pool or not variable_pool.environment_variables:
            return {}

        # 环境变量是Variable对象列表，需要转换为字典
        env_vars = {}
        for var in variable_pool.environment_variables:
            env_vars[var.name] = var.get_value()

        return env_vars
