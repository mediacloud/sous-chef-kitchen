"""
Data models shared between the backend and client.
"""

from pydantic import BaseModel, Field, computed_field


class SousChefKitchenAuthStatus(BaseModel):
    """Status of Sous Chef Kitchen authorization."""

    media_cloud_authorized: bool = Field(False, title="Media Cloud Authorized")
    sous_chef_authorized: bool = Field(False, title="Sous Chef Authorized")

    @computed_field
    @property
    def authorized(self) -> bool:
        """Whether the user is authorized with both Media Cloud and Sous Chef."""

        return self.media_cloud_authorized and self.sous_chef_authorized


class SousChefKitchenSystemStatus(BaseModel):
    """Status of Sous Chef Kitchen backend system components."""

    connection_ready: bool = Field(False, title="Sous Chef Kitchen Connection")
    kitchen_api_ready: bool = Field(False, title="Sous Chef Kitchen API")
    prefect_cloud_ready: bool = Field(False, title="Prefect Cloud")
    prefect_work_pool_ready: bool = Field(False, title="Prefect Work Pool")
    prefect_workers_ready: bool = Field(False, title="Prefect Workers")

    @computed_field
    @property
    def ready(self) -> bool:
        """Whether all Sous Chef Kitchen backend system components are ready."""

        return (
            self.connection_ready
            and self.kitchen_api_ready
            and self.prefect_cloud_ready
            and self.prefect_work_pool_ready
            and self.prefect_workers_ready
        )
