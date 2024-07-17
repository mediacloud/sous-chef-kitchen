import streamlit as st
from streamlit_tags import st_tags
from flow import SousChefBaseOrder
from prefect_client import SousChefClient
import yaml
import asyncio

dep = yaml.safe_load(open("prefect.yaml").read())
deployment_name = dep["deployments"][0]["name"]

async def run_order(order):
	deployment_client = SousChefClient(deployment_name)

	await deployment_client.run_deployment(parameters={"data":order.dict()})


q = st.text_area("Querytext")
start_date = st.date_input('Start Date')
end_date = st.date_input('End Date')
collections = st_tags(label="Collections",
					  text="Press enter to add more",
					  value=["34412234"]
						)
run_name = st.text_input("Run Name", "buffet_test")
s3_prefix = st.text_input("s3 prefix", "mediacloud")

email_to = st_tags(label="email to",
					text="Press enter to add more",
					value=["pgulley@mediacloud.org"]
					)

go = st.button("Submit run")
if go:
	order = SousChefBaseOrder(
			QUERY=q,
			START_DATE_STR=start_date.strftime("%Y-%m-%d"),
			END_DATE_STR=end_date.strftime("%Y-%m-%d"),
			COLLECTIONS=collections,
			NAME=run_name,
			S3_PREFIX=s3_prefix,
			EMAIL_TO=email_to
		)
	loop = asyncio.run(run_order(order))


