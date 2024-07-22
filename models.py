from pydantic import BaseModel, computed_field


class SousChefBaseOrder(BaseModel):
	API_KEY_BLOCK:str = "default"
	QUERY:str = ""
	START_DATE_STR:str = "2024-01-01"
	END_DATE_STR:str = "2024-02-01"
	COLLECTIONS: list[str] = ["34412234"]
	NAME: str = "Sous-Chef-Run"
	S3_PREFIX:str="mediacloud"
	EMAIL_TO:list[str] = ["paige@mediacloud.org"]


	#We'll want some additional validators here on the date probably
	#or maybe to have a transformed output function instead of relying on .dict()
	@computed_field()
	def START_DATE(self) -> str:
		return f"'{self.START_DATE_STR}'"

	@computed_field()
	def END_DATE(self) -> str:
		return f"'{self.END_DATE_STR}'"