from souschef_client import SousChefClient
from models import SousChefBaseOrder
from flask import Flask, jsonify, render_template, send_file, request
import mediacloud.api
import datetime
from typing import List, Callable

app = Flask(__name__, template_folder="buffet_app/templates")
client = SousChefClient()

"""
#Authentication is neccesary before any deployment! But- we can develop around it for now
class MCAuthMiddleware(BaseHTTPMiddleware):
	def __init(self, app: Callable):
		super().__init__(app)

	async def dispatch(self, request: Request, call_next):
		token = request.cookies.get("mediacloud-api-token")
		if not token:
			raise HTTPException(status_code=401, detail="Not allowed")
		
		response = await call_next(request)
		return response


#Quick and dirty authentication via the mediacloud api
@app.get("/login")
async def mc_auth(email:str, api_key:str):
	mc_search = mediacloud.api.SearchApi(api_key)
	try:
		#If I can make an expanded story_list call, I should be able to use sous-chef
		mc_search.story_list("mediacloud", start_date=datetime.date.today(), end_date=datetime.date.today()-datetime.timedelta(1),expanded=True)
	except RuntimeError:
		raise HTTPException(status_code=401, detail="not allowed")
	else:
		response.set_cookie(key="user-email", value=email)
		response.set_cookie(key="mediacloud-api-token", value=api_key)
		return {"message": "Authentication Successful"}

"""

@app.route("/")
def main():
   return send_file("buffet_app/static/main.html")

@app.route("/style.css")
def style():
	return send_file("buffet_app/static/style.css")

# get_all_runs
@app.get("/all_runs")
async def all_runs(tags:List = []):
	runs = await client.all_runs(tags=tags)
	return runs

@app.get("/menu")
async def menu():
	return SousChefBaseOrder.model_json_schema()
	#For now this is just the one schema, but this could be for 


@app.get("/run/<run_id>")
async def get_run(run_id):
	run = await client.get_run(run_id)
	return run



