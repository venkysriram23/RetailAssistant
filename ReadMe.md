## Setup python virtual environment
python -m venv .venv

## Activate python environment
source .venv/bin/activate

## Install dependencies
pip install -r code/requirements.txt

## Configure Google-Gemini API-Key
Visit https://aistudio.google.com/api-keys to find key 
Create a .env file and add
GOOGLE_API_KEY='key-value'

## Create local database by running following command
python3 sql.py

## Open streamlit app
streamlit run code/app.py
