from pydantic import BaseModel, computed_field
from datetime import date

class SousChefBaseOrder(BaseModel):
	API_KEY_BLOCK:str = "default"
	QUERY:str = ""
	START: date = date(2024,1,1)
	END: date = date(2024,2,1)
	COLLECTIONS: list[str] = ["34412234"]
	NAME: str = "Sous-Chef-Run"
	S3_PREFIX:str="mediacloud"
	EMAIL_TO:list[str] = ["paige@mediacloud.org"]


	#We'll want some additional validators here on the date probably
	#or maybe to have a transformed output function instead of relying on .dict()
	@computed_field()
	def START_DATE(self) -> str:
		return f"'{self.START.strftime("%Y-%m-%d")}'"

	@computed_field()
	def END_DATE(self) -> str:
		return f"'{self.END.strftime("%Y-%m-%d")}'"