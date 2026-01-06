.PHONY: run test

run:
	streamlit run app/streamlit_app.py

test:
	pytest -q
