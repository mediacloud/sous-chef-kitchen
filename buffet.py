import streamlit as st
from streamlit_tags import st_tags
from streamlit_modal import Modal
from models import SousChefBaseOrder
from souschef_client import SousChefClient
from prefect.client.schemas.objects import StateType
import yaml
import asyncio
import time
import os

dep = yaml.safe_load(open("prefect.yaml").read())
deployment_name = dep["deployments"][0]["name"]
title = "Sous-Chef Buffet"

deployment_client = SousChefClient()

st.set_page_config(
	page_title="Mediacloud Buffet",
	page_icon="🍽️"
)

def get_recipes():
	recipes = os.listdir("recipes")
	return [r.split(".")[0] for r in recipes]

available_recipes = get_recipes()

def email_to_secret_name(email):
	return f"{email.split("@")[0]}-mc-api-secret"


if "email_checked" not in st.session_state:
	st.session_state.email_checked = False
if "secret_exists" not in st.session_state:
	st.session_state.secret_exists = False
if "email_list" not in st.session_state:
	st.session_state.email_list = ["paige@mediacloud.org"]
if "run_submitted" not in st.session_state:
	st.session_state.run_submitted = False
if "run_status_name" not in st.session_state:
	st.session_state.run_status_name = "Waiting"
if "run_status" not in st.session_state:
	st.session_state.run_status = None

st.session_state.disable_run_button = not st.session_state.secret_exists


async def secret_exists(key_name):
	st.session_state.secret_exists = await deployment_client.check_secret_exists(key_name)
	st.session_state.email_checked = True
	st.rerun()

async def create_secret(key_name, secret):
	key_name = await deployment_client.get_or_create_secret(key_name, secret)
	if key_name:
		st.session_state.secret_exists = True
		st.rerun()


@st.experimental_dialog("User Info", width="large")
def get_user_info():
	st.write("The user information used to authenticate via Mediacloud")
	email = st.text_input("User Email")
	key_name = email_to_secret_name(email)

	if st.button("Submit Email"):
		st.session_state.key_name = key_name
		st.session_state.email_list.extend([email])
		asyncio.run(secret_exists(key_name))

	if st.session_state.email_checked:
		if st.session_state.secret_exists:
			st.success("Good to Go")
		else:
			st.write(f"API key needed for {email}")
			api_key = st.text_input("Mediacloud API Key")
			if st.button("Submit"):
				asyncio.run(create_secret(key_name, api_key))

if not st.session_state.secret_exists:
	get_user_info()
else:

	st.subheader(f"Sous-Chef Buffet: {deployment_name}")

	recipe = st.selectbox("Recipe", available_recipes)

	q = st.text_area("Query text")

	col1, col2 = st.columns(2)

	with col1:
		start_date = st.date_input('Start Date')
		collections = st_tags(label="Collections",
						text="Press enter to add more",
						value=["34412234"],
						)

	with col2:
		end_date = st.date_input('End Date')

		email_to = st_tags(label="email to",
						text="Press enter to add more",
						value=st.session_state.email_list,
						)

	with st.expander("Advanced"):
		run_name = st.text_input("Run Name", "buffet_test")
		s3_prefix = st.text_input("s3 prefix", "mediacloud")


	async def run_order(recipe, order):
		try:
			run = await deployment_client.start_deployment(deployment_name=deployment_name, parameters={"recipe_name":recipe, "data":order.dict()})
		except RuntimeError:
			st.error("SC Buffet run already running!")
		else:

			if run:
				st.session_state.run = run
				st.session_state.run_submitted = True
			print("...")

	async def run_status_loop(run, status):
		with status:
			with st.spinner(f"Working...") as spinner:
				status_indicator = status.empty()
				while True:
					updated_run = await deployment_client.get_run(st.session_state.run.id)
					st.session_state.run_status = updated_run["state_type"]
					st.session_state.run_status_name = updated_run["state_name"]
					status_indicator.write(f"Status is: {st.session_state.run_status_name}")
					if updated_run["state_type"] in [StateType.RUNNING, StateType.SCHEDULED,StateType.PENDING]:
						time.sleep(10)
					else:
						break

			status_indicator.write(f"Status is: {st.session_state.run_status_name}")

	async def get_run_info(run, field):
		value = await deployment_client.get_run(st.session_state.run.id)
		field.write(value)

	go = st.button("Submit run", disabled=st.session_state.disable_run_button)
	if go:
		order = SousChefBaseOrder(
				API_KEY_BLOCK=st.session_state.key_name,
				QUERY=q,
				START=start_date,
				END=end_date,
				COLLECTIONS=collections,
				NAME=run_name,
				S3_PREFIX=s3_prefix,
				EMAIL_TO=email_to
			)
		loop = asyncio.run(run_order(recipe, order))

	status = st.container()

	if st.session_state.run_submitted:
		status.write("Run submitted")
		st.session_state.disable_run_button = True
		asyncio.run(run_status_loop(st.session_state.run, status))
		
			
	if st.session_state.run_status == StateType.COMPLETED:
		status.success("Run completed successfully, you should have an email in your inbox now!")

	if st.session_state.run_status == StateType.FAILED:
		status.error("Run Failed- contact paige@mediacloud.org for assistance")
		asyncio.run(get_run_info(st.session_state.run, status))
