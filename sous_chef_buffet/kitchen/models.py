"""
Data models only used by the Sous Chef Kitchen backend.
"""

import os
from datetime import date

from pydantic import BaseModel, Field, computed_field

DATE_STR_FORMAT = "%Y-%m-%d"
API_AUTH_KEY = os.getenv("SC_API_AUTH_KEY")
DEFAULT_EMAIL_NOTIFICATION_LIST = os.getenv(
    "SC_DEFAULT_NOTIFICATION_EMAIL_LIST", "paige@mediacloud.org").split(",")
    # TODO: Replace with paige@mediacloud.org as default after testing

class SousChefBaseOrder(BaseModel):
    """Definition of a Sous Chef Buffet order."""
    
    API_KEY_BLOCK: str = Field(title="Prefect block with a Media Cloud API key")
    QUERY: str = Field(title="Query parameter for the QueryOnlineNews atom")
    START: date = Field(title="Start date for the QueryOnlineNews atom")
    END: date = Field(title="End date for the QueryOnlineNews atom")
    COLLECTIONS: list[str] = Field(title="Media Cloud collections list")
    NAME: str = Field(title="Name to give the run for this order")
    S3_PREFIX: str = Field(title="S3 prefix to give the output from this order")
    EMAIL_TO: list[str] = Field(DEFAULT_EMAIL_NOTIFICATION_LIST, title="Email notification list")

    @computed_field()
    def START_DATE(self) -> str:
        """Start date formatted for further use by Sous Chef."""
        return f"'{self.START.strftime(DATE_STR_FORMAT)}'"
    
    @computed_field()
    def END_DATE(self) -> str:
        """End date formatted for further use by Sous Chef."""
        return f"'{self.END.strftime(DATE_STR_FORMAT)}'"


#class EntitiesOrder(SousChefBaseOrder):
#        NER_MODEL_NAME: str = ""

