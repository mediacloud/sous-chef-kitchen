import streamlit as st
from streamlit_tags import st_tags
from streamlit_modal import Modal
from models import SousChefBaseOrder
from prefect_client import SousChefClient
import yaml
import asyncio

dep = yaml.safe_load(open("prefect.yaml").read())
deployment_name = dep["deployments"][0]["name"]


deployment_client = SousChefClient()

st.set_page_config(
	page_title="Mediacloud Buffet: Sous-Chef",
	layout="wide",
	page_icon="🍽️"
)

def email_to_secret_name(email):
	return f"{email.split("@")[0]}-mc-api-secret"


if "email_checked" not in st.session_state:
	st.session_state.email_checked = False
if "secret_exists" not in st.session_state:
	st.session_state.secret_exists = False
if "email_list" not in st.session_state:
	st.session_state.email_list = ["paige@mediacloud.org"]

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


st.subheader(f"Configuration for : {deployment_name}")
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


async def run_order(order):
	print("Running...")
	await deployment_client.run_deployment(deployment_name=deployment_name, parameters={"data":order.dict()})

st.write(st.session_state)

go = st.button("Submit run", disabled=st.session_state.disable_run_button)
if go:
	order = SousChefBaseOrder(
			API_KEY_BLOCK=st.session_state.key_name,
			QUERY=q,
			START_DATE_STR=start_date.strftime("%Y-%m-%d"),
			END_DATE_STR=end_date.strftime("%Y-%m-%d"),
			COLLECTIONS=collections,
			NAME=run_name,
			S3_PREFIX=s3_prefix,
			EMAIL_TO=email_to
		)
	loop = asyncio.run(run_order(order))


